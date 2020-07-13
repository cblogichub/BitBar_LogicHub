#!/usr/bin/env PYTHONIOENCODING=UTF-8 /usr/local/bin/python3

# <bitbar.title>LogicHub Utils: Stuff Chad Wanted (because OCD sucks)</bitbar.title>
# <bitbar.version>v2.0 beta</bitbar.version>
# <bitbar.author>Chad Roberts</bitbar.author>
# <bitbar.author.github>deathbywedgie</bitbar.author.github>
# <bitbar.desc>Various helpful actions for LogicHub engineers</bitbar.desc>
# <bitbar.dependencies>See readme.md</bitbar.dependencies>

import base64
import configobj
import json
import os
import re
import sqlparse
import subprocess
import shlex
import sys
from collections import namedtuple
from dataclasses import dataclass
from dataclasses_json import dataclass_json

import clipboard

# Global static variables
user_config_file = "logichub_tools.ini"

# Will be updated if enabled via the config file
debug_enabled = False


def _validate_command(cmd: str or bytes or list or tuple):
    """
    Verify command format. Accepts string, bytes, list of strings, or tuple of strings,
    and returns a formatted command ready for the subprocess.run() method
    :param cmd: Desired shell command in any supported format
    :return formatted_cmd: List of split command parts
    """
    if type(cmd) is bytes:
        # convert to a string; further convert as a string in the next step
        cmd = cmd.decode('utf-8')
    if type(cmd) is str:
        cmd = cmd.strip()
    if not cmd:
        raise ValueError("No command provided")
    elif "|" in cmd or (isinstance(cmd, (list, tuple)) and "|" in ','.join(cmd)):
        raise ValueError("Pipe commands not supported at this time")
    elif isinstance(cmd, (list, tuple)):
        # If the command is already a list or tuple, then assume it is already ready to be used
        return cmd
    # At this point the command must be a string format to continue.
    if type(cmd) is str:
        # Use shlex to split into a list for subprocess input
        formatted_cmd = shlex.split(cmd.strip())
        if not formatted_cmd or type(formatted_cmd) is not list:
            raise ValueError("Command failed to parse into a valid list of parts")
    else:
        raise TypeError(f"Command validation failed: type {type(cmd).__name} not supported")
    return formatted_cmd


def _run_cli_command(cmd, timeout: int = 30, test: bool = True, capture_output: bool = True):
    """
    Reusable method to standardize CLI calls

    :param cmd: Command to execute (can be string or list)
    :param cmd: Timeout in seconds (default 30)
    :param bool test: Whether to test that the command completed successfully (default True)
    :param bool capture_output: Whether to capture the output or allow it to pass to the terminal. (Usually True, but False for things like prompting for the sudo password)
    :return:
    """
    # Also tried these, but settled on subprocess.run:
    # subprocess.call("command1")
    # subprocess.call(["command1", "arg1", "arg2"])
    # or
    # import os
    # os.popen("full command string")
    print_debug(f"Executing command: {cmd}")
    _cmd = _validate_command(cmd)
    _result = subprocess.run(_cmd, capture_output=capture_output, universal_newlines=True, timeout=timeout)
    if test:
        _result.check_returncode()
    return _result


def _run_shell_command_with_pipes(command, print_result=True, indent: int = 5):
    """Simple version for now. May revisit later to improve it."""
    print_debug(f"Executing command: {command}")
    _output = subprocess.getoutput(command)
    if print_result:
        if indent > 0:
            for _line in _output.split('\n'):
                print(" " * indent + _line)
        else:
            print(_output)
    return _output


def do_prompt_for_sudo():
    # If a sudo session is not already active, auth for sudo and start the clock.
    # This function can be called as many times as desired to and will not cause re-prompting unless the timeout has been exceeded.
    _ = _run_cli_command('sudo -v -p "sudo password: "', timeout=None, test=True, capture_output=False)


def convert_boolean(_var):
    if type(_var) is str:
        _var2 = _var.strip().lower()
        if _var2 in ["yes", "true"]:
            return True
        elif _var2 in ["no", "false"]:
            return False
    return _var


def sort_dict(_var):
    _safe_dict = json.loads(json.dumps(_var))
    if _safe_dict is list:
        return sorted(_safe_dict)
    elif not isinstance(_safe_dict, dict):
        return convert_boolean(_safe_dict)
    new_dict = {}
    for _key in sorted(_safe_dict.keys()):
        new_value = sort_dict(_safe_dict[_key])
        new_dict[_key] = new_value
    return new_dict


def print_debug(msg):
    if debug_enabled:
        print(f"[DEBUG] {msg}")


@dataclass_json
@dataclass
class ConfigMain:
    # Path to the BitBar repo. No default here, as this is a required field.
    bitbar_repo_path: str

    # Local user ID. If not provided, user will be drawn from USER environment variable
    local_user: str

    # Default SSH username. If not provided, user will be drawn from USER environment variable
    ssh_user: str

    # SSH keys are assumed to be located in ~/.ssh unless a full path is provided
    ssh_key: str

    # Return either "Dark" or "Light" for the OS theme
    os_theme: str

    # Usually "lo0"
    default_loopback_interface: str


@dataclass_json
@dataclass
class ConfigBitBar:
    # Define how this plugin should appear in the status bar
    # Options: logo, text, both, custom
    status_bar_style: str

    # Text for the BitBar plugin label (not used if status_bar_style is set to logo)
    # If status_bar_style is set to "custom", you can specify additional formatting criteria according to BitBar's plugin API
    status_bar_label: str

    # Choose the logo: small, large, xl
    status_bar_icon_size: str

    # Override the color of the text in the status bar (ignored if text is disabled by the selected style)
    status_bar_text_color: str

    # Generate a popup notification every time the clipboard gets updated
    clipboard_update_notifications: bool

    # Show debug output
    debug_output_enabled: bool

    # default Jira prefix (project name)
    jira_default_prefix: str


@dataclass_json
@dataclass
class ConfigBitBarNetworking:
    configs: dict


# ToDo Finish this new feature
@dataclass_json
@dataclass
class ConfigBitBarCustom:
    def __post_init__(self):
        pass


@dataclass_json
@dataclass
class Config:
    main: ConfigMain = None
    BitBar: ConfigBitBar = None
    BitBar_custom: ConfigBitBarCustom = None
    BitBar_networking: ConfigBitBarNetworking = None

    def __post_init__(self):
        config_sections = ["main", "BitBar", "BitBar_networking", "BitBar_custom"]

        # initialize a config obj for the user's logichub_tools.ini file
        self.user_settings_dict = configobj.ConfigObj(os.path.join(os.environ.get("HOME"), user_config_file))
        if not self.user_settings_dict:
            print(f"{user_config_file} not found")
            sys.exit(1)
        else:
            for k in config_sections:
                if k not in self.user_settings_dict:
                    self.user_settings_dict[k] = {}

        self.get_config_main(**self.user_settings_dict["main"])
        if not self.main.bitbar_repo_path:
            print("bitbar_repo_path not set in logichub_tools.ini")
            sys.exit(1)

        self.get_config_bitbar_params(**self.user_settings_dict["BitBar"])
        self.get_config_bitbar_networking_params(**self.user_settings_dict["BitBar_networking"])
        self.BitBar_custom = ConfigBitBarCustom()

        # Find the path to the home directory
        self.dir_user_home = os.environ.get("HOME")

        # initialize a config obj for the user's logichub_tools.ini file
        user_config_file_path = os.path.join(self.dir_user_home, user_config_file)
        user_settings = configobj.ConfigObj(user_config_file_path)

        self.default_loopback_interface = self.main.default_loopback_interface
        self.local_user = self.main.local_user
        self.default_ssh_key = self.main.ssh_key
        if "/" not in self.default_ssh_key:
            self.default_ssh_key = os.path.join(self.dir_user_home, ".ssh", self.default_ssh_key)

        self.debug_enabled = self.BitBar.debug_output_enabled
        self.dir_internal_tools = self.main.bitbar_repo_path
        self.dir_supporting_scripts = os.path.join(self.dir_internal_tools, "scripts")
        self.image_file_path = os.path.join(self.dir_internal_tools, 'supporting_files/images')

        logos_by_os_theme = {
            "Dark": {
                "small": "bitbar_status_small.png",
                "large": "bitbar_status_large_dark.png",
                "xl": "bitbar_status_xlarge_dark.png",
            },
            "Light": {
                "small": "bitbar_status_small.png",
                "large": "bitbar_status_large.png",
                "xl": "bitbar_status_xlarge.png",
            }
        }
        self.status_bar_logo = logos_by_os_theme[self.main.os_theme][self.BitBar.status_bar_icon_size]

        self.status_bar_style = self.BitBar.status_bar_style
        self.status_bar_label = self.BitBar.status_bar_label
        self.status_bar_text_color = self.BitBar.status_bar_text_color
        self.clipboard_update_notifications = self.BitBar.clipboard_update_notifications
        self.jira_default_prefix = self.BitBar.jira_default_prefix

    def get_config_main(self, **kwargs):
        self.main = ConfigMain(
            bitbar_repo_path=kwargs.get("bitbar_repo_path", None),
            local_user=kwargs.get("local_user", os.environ.get("USER")),
            ssh_user=kwargs.get("ssh_user", os.environ.get("USER")),
            ssh_key=kwargs.get("ssh_key", "id_rsa"),
            os_theme=kwargs.get("os_theme", os.popen('defaults read -g AppleInterfaceStyle 2> /dev/null').read().strip() or "Light"),
            default_loopback_interface=kwargs.get("default_loopback_interface", "lo0")
        )

    def get_config_bitbar_params(self, **kwargs):
        self.BitBar = ConfigBitBar(
            status_bar_style=kwargs.get("status_bar_style", "logo"),
            status_bar_label=kwargs.get("status_bar_label", "LHUB"),
            status_bar_icon_size=kwargs.get("status_bar_icon_size", "large"),
            status_bar_text_color=kwargs.get("status_bar_text_color", "black"),
            clipboard_update_notifications=convert_boolean(kwargs.get("clipboard_update_notifications", False)),
            debug_output_enabled=convert_boolean(kwargs.get("debug_output_enabled", False)),
            jira_default_prefix=kwargs.get("jira_default_prefix", "LHUB")
        )

    def get_config_bitbar_networking_params(self, **kwargs):
        self.BitBar_networking = ConfigBitBarNetworking(kwargs)


class BitBar:
    ssh_tunnel_configs = []
    port_redirect_configs = []

    def __init__(self):
        self.title_default = "LogicHub_Utils"
        self.title_json = "JsonUtils"
        self.notification_json_invalid = 'Invalid JSON !!!!!!!!!!'
        self.script_name = sys.argv[0]
        self.status = ""
        self.bitbar_menu_output = ""

        self.url_jira = r"https://logichub.atlassian.net/browse/{}"
        self.url_uws = r"https://www.ultimatewindowssecurity.com/securitylog/encyclopedia/event.aspx?eventID={}"
        self.url_nmap = r"https://nmap.org/nsedoc/scripts/{}"

        self.config = Config()

        if self.config.debug_enabled:
            global debug_enabled
            debug_enabled = self.config.debug_enabled
        self.set_status_bar_display()
        self.loopback_interface = self.config.default_loopback_interface

        # dict to store all of the actions
        self.action_list = {}

        # ------------ Menu Section: LogicHub ------------ #

        self.add_menu_section("LogicHub | image={} size=20 color=blue".format(self.image_to_base64_string("bitbar_menu_logichub.ico")))
        self.print_in_bitbar_menu("LQL & Web UI")
        self.make_action("(Beta) Pretty Print SQL", self.logichub_pretty_print_sql)
        self.make_action("(Beta) Pretty Print SQL options", action=None, alternate=True)
        self.make_action("Wrapped at 80 characters", self.logichub_pretty_print_sql_wrapped, menu_depth=2)
        self.make_action("Compact", self.logichub_pretty_print_sql_compact, menu_depth=2)

        self.make_action("Tabs to commas", self.logichub_tabs_to_columns)
        self.make_action("Tabs to commas (force lowercase)", self.logichub_tabs_to_columns_lowercase, alternate=True)
        self.make_action("Tabs to commas & quotes", self.logichub_tabs_to_columns_and_quotes)
        self.make_action("Tabs to commas & quotes (force lowercase)", self.logichub_tabs_to_columns_and_quotes_lowercase, alternate=True)
        self.make_action("SQL New (from table name)", self.logichub_sql_start_from_table_name)
        self.make_action("SQL New (without table name)", self.logichub_sql_start_without_table_name, alternate=True)
        self.make_action("SQL Start from spaced strings", self.logichub_sql_start_from_tabs)
        self.make_action("SQL Start from spaced strings (sorted)", self.logichub_sql_start_from_tabs_sorted)
        self.make_action("SQL Start from spaced strings (distinct)", self.logichub_sql_start_from_tabs_distinct)
        self.make_action("SQL Start from spaced strings (join with left columns)", self.logichub_sql_start_from_tabs_join_left)
        self.make_action("SQL Start from spaced strings (join, left columns only)", self.logichub_tabs_to_columns_left_join, alternate=True)
        self.make_action("SQL Start from spaced strings (join with right columns)", self.logichub_sql_start_from_tabs_join_right)
        self.make_action("SQL Start from spaced strings (join, right columns only)", self.logichub_tabs_to_columns_right_join, alternate=True)
        self.make_action("Operator Start: autoJoinTables", self.logichub_operator_start_autoJoinTables)
        self.make_action("Operator Start: jsonToColumns", self.logichub_operator_start_jsonToColumns)
        self.make_action("Event File URL from File Name", self.logichub_event_file_URL_from_file_name)
        self.make_action("Event File URL path (static)", self.logichub_event_file_URL_static, alternate=True)

        self.print_in_bitbar_menu("Shell: Host")
        self.make_action("Add myself to docker group", self.shell_lh_host_fix_add_self_to_docker_group)
        self.make_action("Own Instance Version", self.logichub_shell_own_instance_version)
        self.make_action("Path to service container data", self.shell_lh_host_path_to_service_container_volume)
        self.make_action("Recent UI user activity", self.logichub_check_recent_user_activity)
        self.make_action("Stop and Start All Services", self.logichub_stop_and_start_services_in_one_line)

        self.print_in_bitbar_menu("Shell: Service Container")
        self.make_action("List Edited Descriptors", self.lh_service_shell_list_edited_descriptors)

        self.print_in_bitbar_menu("Docker")
        self.make_action("service bash", self.docker_service_bash)
        self.make_action("psql", self.docker_psql)

        self.print_in_bitbar_menu("DB: Postgres")
        self.make_action("List Descriptors w/ Docker Images", self.db_postgres_descriptors_and_docker_images)
        self.make_action("List Instances w/ Docker Images", self.db_postgres_instances_and_docker_images)
        self.make_action("List Instances w/ Docker Images (extended)", self.db_postgres_instances_and_docker_images_extended, alternate=True)
        self.make_action("List Instances w/ Docker Images, exclude image in clipboard", self.db_postgres_instances_and_docker_images_exclude_image)
        self.make_action("List Instances w/ Docker Images (extended), exclude image in clipboard", self.db_postgres_instances_and_docker_images_extended_exclude_image, alternate=True)

        # ToDo Update the actions above to give each an alternate version which runs without having to go into psql first

        self.print_in_bitbar_menu("Integrations")
        self.make_action("integrationsFiles path: LogicHub host", self.clipboard_integrationsFiles_path_logichub_host)
        self.make_action("integrationsFiles path: LogicHub host (from file name)", self.clipboard_integrationsFiles_path_logichub_host_from_file_name, alternate=True)
        self.make_action("integrationsFiles path: integration containers", self.clipboard_integrationsFiles_path_integration_containers)
        self.make_action("integrationsFiles path: integration containers (from file name)", self.clipboard_integrationsFiles_path_integration_containers_from_file_name, alternate=True)
        self.make_action("integrationsFiles path: service container", self.clipboard_integrationsFiles_path_service_container)
        self.make_action("integrationsFiles path: service container (from file name)", self.clipboard_integrationsFiles_path_service_container_from_file_name, alternate=True)

        self.make_action("Copy descriptor file using its image tag", self.copy_descriptor_file_using_image_tag)
        self.make_action("Copy descriptor file using its image tag, then edit original", self.copy_descriptor_file_using_image_tag_then_edit_original, alternate=True)

        self.make_action("Open bash in docker container by product name", self.open_integration_container_by_product_name)

        self.print_in_bitbar_menu("LogicHub Upgrades")
        self.make_action("Upgrade Prep: Visual inspection", self.logichub_upgrade_prep_verifications)
        self.make_action("Upgrade Prep: Backups (run sudo -v as logichub/centos first!)", self.logichub_upgrade_prep_backups)

        self.add_menu_divider_line(menu_depth=1)

        self.make_action("Upgrade Command (from milestone version in clipboard)", self.logichub_upgrade_command_from_clipboard)
        self.make_action("Upgrade Command (static)", self.logichub_upgrade_command_static, alternate=True)
        self.make_action("Upgrade Command with Backup Script (from milestone version in clipboard)", self.logichub_upgrade_command_from_clipboard_with_backup_script)
        self.make_action("Upgrade Command with Backup Script (static)", self.logichub_upgrade_command_static_with_backup_script, alternate=True)

        # ------------ Menu Section: Networking ------------ #
        # First check whether there are any custom networking configs (i.e. ssh tunnels or port redirects)
        self.check_for_custom_networking_configs()

        self.add_menu_section("Networking | image={} size=20 color=blue".format(self.image_to_base64_string("bitbar_menu_ssh.png")))

        self.print_in_bitbar_menu("Reset")
        self.make_action("Terminate SSH tunnels", self.action_terminate_tunnels, terminal=True)
        self.make_action("Terminate Local Port Redirection", self.action_terminate_port_redirection, terminal=True)
        self.make_action("Terminate All", self.action_terminate_all, terminal=True)

        self.print_in_bitbar_menu("Port Redirection")
        # If custom redirect configs are defined in logichub_tools.ini, then add actions for each
        for _config in self.port_redirect_configs:
            self.make_action(_config[0], self.port_redirect_custom, terminal=True, action_id=_config[1])

        self.print_in_bitbar_menu("SSH Tunnels (custom)")
        # If custom ssh configs are defined in logichub_tools.ini, then add actions for each
        for _config in self.ssh_tunnel_configs:
            self.make_action(_config[0], self.ssh_tunnel_custom, terminal=True, action_id=_config[1])

        # ------------ Menu Section: TECH ------------ #

        self.add_menu_section(":wrench: TECH | size=20 color=blue")

        self.print_in_bitbar_menu("JSON")
        self.make_action("JSON Validate", self.json_validate)
        self.make_action("JSON Format", self.json_format)
        self.make_action("JSON Compact", self.json_compact)
        self.make_action("JSON Fix (escaped strings to dicts/lists)", self.action_json_fix)

        self.print_in_bitbar_menu("Link Makers")

        self.make_action("Jira: Open Link from ID", self.make_link_jira_and_open)
        self.make_action("Jira: Make Link from ID", self.make_link_jira, alternate=True)
        self.make_action("UWS: Open link from Windows event ID", self.make_link_uws_and_open)
        self.make_action("UWS: Make link from Windows event ID", self.make_link_uws, alternate=True)
        self.make_action("Nmap: Open link to script documentation", self.make_link_nmap_script_and_open)
        self.make_action("Nmap: Make link to script documentation", self.make_link_nmap_script, alternate=True)

        self.print_in_bitbar_menu("Shell Commands (general)")

        # Visual Mode, Permanent
        self.make_action("vim: visual mode - disable permanently", self.shell_vim_visual_mode_disable_permanently)
        self.make_action("vim: visual mode - enable permanently", self.shell_vim_visual_mode_enable_permanently, alternate=True)

        # Visual Mode, Temporary (within an active session)
        self.make_action("vim: visual mode - disable within a session", self.shell_vim_visual_mode_disable_within_session)
        self.make_action("vim: visual mode - enable within a session", self.shell_vim_visual_mode_enable_within_session, alternate=True)

        # Show Line Numbers, Permanent
        self.make_action("vim: line numbers - enable permanently", self.shell_vim_line_numbers_enable_permanently)
        self.make_action("vim: line numbers - disable permanently", self.shell_vim_line_numbers_disable_permanently, alternate=True)

        # Show Line Numbers, Temporary (within an active session)
        self.make_action("vim: line numbers - enable within a session", self.shell_vim_line_numbers_enable_within_session)
        self.make_action("vim: line numbers - disable within a session", self.shell_vim_line_numbers_disable_within_session, alternate=True)

        # Disable visual mode AND enable line numbers all at once
        self.make_action("vim: Set both permanently", self.shell_vim_set_both_permanently)

        self.print_in_bitbar_menu("Text Editing")
        self.make_action("Text to Uppercase", self.text_make_uppercase)
        self.make_action("Text to Lowercase", self.text_make_lowercase)
        self.make_action("Trim Text in Clipboard", self.text_trim_string)
        self.make_action("Remove Text Formatting", self.text_remove_formatting)

        # Lastly, attempt to get the BitBar version and print it as an FYI
        try:
            with open("/Applications/BitBar.app/Contents/Info.plist", "r") as app_file:
                _app_info = app_file.read()
                bitbar_version = re.findall('<key>CFBundleVersion<.*\s+<string>(.*?)</string>', _app_info)[0]
                if bitbar_version:
                    self.print_in_bitbar_menu(f"---\nBitBar version: {bitbar_version}")
        except:
            pass

    def add_menu_section(self, label, menu_depth=0):
        """
        Print a divider line as needed by BitBar, then print a label for the new section
        :param label:
        :param menu_depth: 0 for top level, 1 for submenu, 2 for first nested submenu, etc.
        :return:
        """
        assert label, "New BitBar section requested without providing a label"
        self.add_menu_divider_line(menu_depth=menu_depth)
        self.print_in_bitbar_menu("--" * menu_depth + label)

    def add_menu_divider_line(self, menu_depth=0):
        """
        Print a divider line in the BitBar Menu
        Menu depth of 0 for top level menu, 1 for first level submenu, 2 for a nested submenu, etc.
        :param menu_depth:
        :return:
        """
        _divider_line = "---" + "--" * menu_depth
        self.print_in_bitbar_menu(_divider_line)

    def print_bitbar_menu_output(self):
        print(self.bitbar_menu_output)

    ############################################################################
    # Reusable functions
    ############################################################################
    def display_notification(self, content, title=None):
        content = content.replace('"', '\\"')
        if not title:
            title = self.title_default
        # subprocess.call(["osascript", "-e", f'display notification "{content}" with title "{title}"'])
        _output = os.popen(f'osascript -e "display notification \\"{content}\\" with title \\"{title}\\""')

    def display_notification_error(self, content, title=None, print_stderr=False):
        _output = os.popen('osascript -e "beep"')
        _error = f"Failed with error: {content}"
        if print_stderr:
            print(f"\n{_error}\n")
        self.display_notification(_error, title)
        sys.exit(1)

    def print_in_bitbar_menu(self, msg):
        if self.bitbar_menu_output:
            self.bitbar_menu_output += "\n"
        self.bitbar_menu_output += msg

    def fail_with_exception(self, msg):
        self.print_in_bitbar_menu('LHUB_FAIL| color=red\n---')
        self.print_in_bitbar_menu(f'FAILED: {msg}| color=red')
        try:
            raise type(msg)(msg)
        except TypeError as e:
            if type(msg) not in [str]:
                raise type(msg)(msg)
        self.display_notification_error(msg)

    def image_to_base64_string(self, file_name):
        file_path = os.path.join(self.config.image_file_path, file_name)
        with open(file_path, "rb") as image_file:
            image_bytes = image_file.read()
            image_b64 = base64.b64encode(image_bytes)
        return image_b64.decode("unicode_escape")

    def set_status_bar_display(self):
        # Ignore status_bar_label is status_bar_style is only the logo
        status_bar_label = "" if self.config.status_bar_style == "logo" else self.config.status_bar_label
        # If the status bar style is "custom," then whatever is passed in status_bar_label is the final product
        if self.config.status_bar_style != "custom":
            status_bar_label += "|"
            if self.config.status_bar_style in ["logo", "both"]:
                logo = self.image_to_base64_string(self.config.status_bar_logo)
                status_bar_label += f" image={logo}"
            if self.config.status_bar_style in ["text", "both"]:
                status_bar_label += f" color={self.config.status_bar_text_color}"
        self.status = status_bar_label

        # Set status bar text and/or logo
        self.print_in_bitbar_menu(self.status)

    def make_action(self, name, action, action_id=None, menu_depth=1, alternate=False, terminal=False):
        menu_name = name
        if menu_depth:
            menu_name = '--' * menu_depth + ' ' + menu_name
        action_string = ''
        if alternate:
            action_string = action_string + ' alternate=true'
        if not action:
            self.print_in_bitbar_menu(f'{menu_name} | {action_string}')
            return

        if not action_id:
            action_id = re.sub(r'\W', "_", name)

        action_tuple = namedtuple("Action", ["id", "name", "action"])
        _var = action_tuple(action_id, name, action)
        self.action_list[action_id] = _var
        terminal = str(terminal).lower()
        self.print_in_bitbar_menu(f'{menu_name} | {action_string} bash="{self.script_name}" param1="{action_id}" terminal={terminal}')
        return _var

    @staticmethod
    def read_clipboard(trim_input=True):
        clip = clipboard.paste()
        if trim_input:
            clip = clip.strip()
        return clip

    def write_clipboard(self, text):
        clipboard.copy(text)
        if self.config.clipboard_update_notifications:
            self.display_notification("Clipboard updated")

    def copy_file_contents_to_clipboard(self, file_path, file_name=None):
        """
        Standardized method for reading a file and copying its contents to the
        clipboard. If only a file_path is passed, assume that it is a full path
        to a file. If file_name is provided, assume file_path is its location,
        and join them automatically before reading the file's contents.

        :param file_path: Location of the file to read
        :param file_name: (optional) Name of the file. If a value is provided,
        file_path will be assumed to be a directory and joined with file_name,
        otherwise file_path will be treated as a full path to a file.
        :return:
        """
        if file_name.strip():
            file_path = os.path.join(file_path, file_name)
        if not os.path.isfile(file_path):
            self.display_notification_error("Invalid path to supporting script")
        with open(file_path, "rU") as f:
            output = f.read()
        self.write_clipboard(output)

    def make_upgrade_command(self, version: str = None):
        if not version:
            version = "XX.YY"
        else:
            # To make sure this works whether or not the leading 'm' is provided, strip out any 'm'
            version = version.replace('m', '').strip()
            if not version.strip() or not re.match(r'^\d{2,}\.\d+$', version):
                self.display_notification_error("Invalid LogicHub version")
        return f"bash <(curl https://s3-us-west-1.amazonaws.com/lhub-installer/installer-m{version}.sh)"

    @staticmethod
    def make_backup_command():
        return "sudo /opt/logichub/scripts/backup.sh"

    @staticmethod
    def pretty_print_sql(input_str, wrap_after=0):
        """
        Reusable method to "pretty print" SQL

        :param input_str:
        :param wrap_after:
        :param output_str:
        :return:
        """
        # Replace line breaks with spaces, then trim leading and trailing whitespace
        _output = re.sub(r'[\n\r]+', ' ', input_str).strip()
        tick_wrapper = False
        # In case copied straight from LogicHub, strip out wrapping ticks, but remember...
        if re.match(r'^`(.*)`$', _output):
            tick_wrapper = True
            _output = re.sub(r'^(`+)([\s\S]+)\1$', r'\2', _output)
        _output = sqlparse.format(_output, reindent=True, keyword_case='upper', indent_width=4, wrap_after=wrap_after, identifier_case=None)
        if tick_wrapper:
            _output = rf"`{_output}`"
            # Realign the "select" section, because alignment is broken when a tick is added to wrap the query
            output_lines = _output.split('\n')
            for line_num in range(len(output_lines)):
                # Only add spaces to the "select" portion
                if output_lines[line_num].upper().startswith("FROM"):
                    break
                elif line_num > 0:
                    output_lines[line_num] = " " + output_lines[line_num]
            _output = '\n'.join(output_lines)
        return _output

    ############################################################################
    # Section:
    #   LogicHub
    ############################################################################

    ############################################################################
    # LogicHub -> LQL & Web UI

    def logichub_pretty_print_sql(self, **kwargs):
        """
        Pretty Print SQL

        :return:
        """
        _input = BitBar.read_clipboard()
        try:
            _output = BitBar.pretty_print_sql(_input, **kwargs)
        except Exception as err:
            self.display_notification_error("Exception from sqlparse: {}".format(repr(err)))
        else:
            self.write_clipboard(_output)

    def logichub_pretty_print_sql_wrapped(self):
        """
        Pretty Print SQL: Wrapped at 80 characters

        :return:
        """
        self.logichub_pretty_print_sql(wrap_after=80)

    def logichub_pretty_print_sql_compact(self):
        """
        Pretty Print SQL: Compact

        :return:
        """
        self.logichub_pretty_print_sql(wrap_after=99999)

    def logichub_tabs_to_columns(self, force_lower=False):
        _input = BitBar.read_clipboard()
        if force_lower:
            _input = _input.lower()
        _columns = _input.split()
        self.write_clipboard("{}".format(", ".join(_columns)))

    def logichub_tabs_to_columns_lowercase(self):
        self.logichub_tabs_to_columns(force_lower=True)

    def logichub_tabs_to_columns_and_quotes(self, force_lower=False):
        _input = BitBar.read_clipboard()
        if force_lower:
            _input = _input.lower()
        _columns = _input.split()
        self.write_clipboard('"{}"'.format('", "'.join(_columns)))

    def logichub_tabs_to_columns_and_quotes_lowercase(self):
        self.logichub_tabs_to_columns_and_quotes(force_lower=True)

    def logichub_sql_start_from_table_name(self):
        _input = BitBar.read_clipboard()
        self.write_clipboard(f'`SELECT * FROM {_input}`')

    def logichub_sql_start_without_table_name(self):
        self.write_clipboard(f'`SELECT * FROM ')

    def logichub_sql_start_from_tabs(self):
        _input = BitBar.read_clipboard()
        _columns = _input.split()
        _columns_formatted = ", ".join(_columns)
        self.write_clipboard(f'`SELECT {_columns_formatted}\nFROM ')

    def logichub_sql_start_from_tabs_sorted(self):
        _input = BitBar.read_clipboard()
        _columns = sorted(_input.split())
        _columns_formatted = ", ".join(_columns)
        self.write_clipboard(f'`SELECT {_columns_formatted}\nFROM ')

    def logichub_sql_start_from_tabs_distinct(self):
        _input = BitBar.read_clipboard()
        _columns = _input.split()
        _columns_formatted = ", ".join(_columns)
        self.write_clipboard(f'`SELECT DISTINCT {_columns_formatted}\nFROM ')

    def logichub_tabs_to_columns_left_join(self):
        _input = BitBar.read_clipboard()
        _columns = _input.split()
        self.write_clipboard("L.{}".format(", L.".join(_columns)))

    def logichub_tabs_to_columns_right_join(self):
        _input = BitBar.read_clipboard()
        _columns = _input.split()
        self.write_clipboard("R.{}".format(", R.".join(_columns)))

    def logichub_sql_start_from_tabs_join_left(self):
        _input = BitBar.read_clipboard()
        _columns = _input.split()
        _columns_formatted = "L.{}".format(", L.".join(_columns))
        self.write_clipboard(f'`SELECT {_columns_formatted}\nFROM xxxx L\nLEFT JOIN xxxx R\nON L.xxxx = R.xxxx`')

    def logichub_sql_start_from_tabs_join_right(self):
        _input = BitBar.read_clipboard()
        _columns = _input.split()
        _columns_formatted = "R.{}".format(", R.".join(_columns))
        self.write_clipboard(f'`SELECT {_columns_formatted}\nFROM xxxx L\nLEFT JOIN xxxx R\nON L.xxxx = R.xxxx`')

    def logichub_operator_start_autoJoinTables(self):
        _input = BitBar.read_clipboard()
        if ' ' in _input:
            self.display_notification_error("Invalid input; table name cannot contain spaces")
        self.write_clipboard(f'autoJoinTables([{_input}, xxxx])')

    def logichub_operator_start_jsonToColumns(self):
        _input = BitBar.read_clipboard()
        if ' ' in _input:
            self.display_notification_error("Invalid input; table name cannot contain spaces")
        self.write_clipboard(f'jsonToColumns({_input}, "result")')

    def logichub_event_file_URL_from_file_name(self):
        _input = BitBar.read_clipboard()
        self.write_clipboard(f'file:///opt/docker/data/service/event_files/{_input}')

    def logichub_event_file_URL_static(self):
        self.write_clipboard(f'file:///opt/docker/data/service/event_files/')

    ############################################################################
    # LogicHub -> Shell: Host
    def shell_lh_host_fix_add_self_to_docker_group(self):
        self.write_clipboard(f'sudo usermod -a -G docker {self.config.local_user}')

    def shell_lh_host_path_to_service_container_volume(self):
        self.write_clipboard(f'/var/lib/docker/volumes/logichub_data/_data/service/')

    def logichub_check_recent_user_activity(self):
        self.write_clipboard(r"""check_recent_user_activity() {
    # New consolidated list of all users who have logged in during the current and previous log files
    previous_service_log="$(find /var/log/logichub/service -name "service.log.2*gz"| sort | tail -n1)"
    users_all=($(sudo zgrep -ohP "Login request: *\K\S+" "${previous_service_log}" /var/log/logichub/service/service.log | sort -u))
    printf "Users who have logged in recently:\n\n"
    printf "    %s\n" "${users_all[@]}" | sort -u | grep -P ".*"

    printf "\n\nLatest activity:\n\n"
    echo "$(for i in ${users_all[@]}; do printf "    $(zgrep -ih "user: ${i}" "${previous_service_log}" /var/log/logichub/service/service.log | grep -P "^\d{4}-" | tail -n1 | grep "${i}")\n"; done)" | sort -u | grep -P "User: \K[^\s\(]+"
    printf "\n\nCurrent date:\n\n"
    printf "    $(TZ=America/Los_Angeles date +"%Y-%m-%d %H:%M:%S (%Z)")\n"
    printf "    $(TZ=UTC date +"%Y-%m-%d %H:%M:%S (%Z)")\n"
    printf "\n"
}
check_recent_user_activity
""")

    def logichub_stop_and_start_services_in_one_line(self):
        self.write_clipboard("sudo /opt/logichub/scripts/stop_logichub_sw.sh ; sleep 5 ; sudo /opt/logichub/scripts/start_logichub_sw.sh")

    def logichub_shell_own_instance_version(self):
        self.write_clipboard(f"""curl -s --insecure https://localhost/api/version | grep -Po '"version" : "\K[^"\s]+'""")

    def copy_descriptor_file_using_image_tag(self):
        """
        Copy descriptor file using its image tag in the file name

        :return:
        """
        _input = BitBar.read_clipboard()
        self.write_clipboard(f"""cp -p "{_input}" "{_input}.$(grep -Po '"image"[ \\t]*:[ \\t]*"\\K[^"]+' "{_input}" | sed -E 's/^.*://')-$(date +'%Y%m%d_%H%M%S')" """)

    def copy_descriptor_file_using_image_tag_then_edit_original(self):
        """
        Copy descriptor file using its image tag, then edit original

        :return:
        """
        _input = BitBar.read_clipboard()
        self.write_clipboard(f"""cp -p "{_input}" "{_input}.$(grep -Po '"image"[ \\t]*:[ \\t]*"\\K[^"]+' "{_input}" | sed -E 's/^.*://')-$(date +'%Y%m%d_%H%M%S')"; vi "{_input}" """)

    def open_integration_container_by_product_name(self):
        """
        Open bash in docker container by product name

        :return:
        """
        self.write_clipboard(r"""lh_open_docker_image_by_product_name() { search_str=$1; [[ -z $search_str ]] && echo && read -p "Type part of the product name: " -r search_str; [[ -z $search_str ]] && echo "No search string provided; aborted" && return; mapfile -t newest < <(docker ps|grep -iP "lhub-managed-integrations.logichub.[^.\s]*$search_str"|head -n1|sed -E 's/ +/\n/g'); [[ -z ${newest[0]} ]] && echo "No matching docker image found" && return; echo; echo "${newest[-1]}"|grep -Po 'logichub\.\K[^.]+'; printf 'Image ID: %s\nImage Name: %s\n\n' ${newest[0]} ${newest[1]}; docker exec -it "${newest[0]}" /bin/bash; }; lh_open_docker_image_by_product_name """)

    ############################################################################
    # LogicHub -> Shell: Service Container

    def lh_service_shell_list_edited_descriptors(self):
        self.write_clipboard("""ls -l /opt/docker/resources/integrations |grep -P "\.json" | grep -v "$(ls -l /opt/docker/resources/integrations |grep -P '\.json$' | awk '{print $6" "$7" "$8}'|sort|uniq -c|sed -E 's/^ *//'|sort -nr|head -n1|grep -Po ' \K.*')\"""")

    ############################################################################
    # LogicHub -> Docker

    def docker_service_bash(self):
        self.write_clipboard('docker exec -it service /bin/bash\n')

    def docker_psql(self):
        self.write_clipboard('docker exec -it postgres psql --u daemon lh\n\\pset pager off\n')

    ############################################################################
    # LogicHub -> DB: Postgres

    def db_postgres_descriptors_and_docker_images(self):
        self.write_clipboard("""select id, modified, substring(descriptor from '"image" *: *"([^"]*?)') as docker_image from integration_descriptors order by id;""")

    @staticmethod
    def _build_query_instances_and_docker_images(extended=False, exclude=False):
        extended_fields = "" if not extended \
            else """integration_id, substring(cast(descriptor::json->'runtimeEnvironment'->'descriptor'->'image' as varchar) from ':([^:]+?)"$') as "Docker tag", """
        query_string = f"""select substring(cast(descriptor::json->'name' as varchar) from '"(.+)"') as "Integration Name", label, id, substring(cast(descriptor::json->'version' as varchar) from '"(.+)"') as "Integration Version", {extended_fields}substring(cast(descriptor::json->'runtimeEnvironment'->'descriptor'->'image' as varchar) from '"(.+)"') as "Full Docker Image" from integration_instances order by integration_id, label"""

        if exclude:
            docker_image = BitBar.read_clipboard()
            return f"""select * from ({query_string}) a where "Full Docker Image" not like '{docker_image}';"""
        else:
            return f"{query_string};"

    def db_postgres_instances_and_docker_images(self):
        self.write_clipboard(BitBar._build_query_instances_and_docker_images(extended=False, exclude=False))

    def db_postgres_instances_and_docker_images_extended(self):
        self.write_clipboard(BitBar._build_query_instances_and_docker_images(extended=True, exclude=False))

    def db_postgres_instances_and_docker_images_exclude_image(self):
        self.write_clipboard(BitBar._build_query_instances_and_docker_images(extended=False, exclude=True))

    def db_postgres_instances_and_docker_images_extended_exclude_image(self):
        self.write_clipboard(BitBar._build_query_instances_and_docker_images(extended=True, exclude=True))

    ############################################################################
    # LogicHub -> Integrations

    def clipboard_integrationsFiles_path_logichub_host(self):
        self.write_clipboard("/var/lib/docker/volumes/logichub_data/_data/shared/integrationsFiles/")

    def clipboard_integrationsFiles_path_logichub_host_from_file_name(self):
        self.write_clipboard("/var/lib/docker/volumes/logichub_data/_data/shared/integrationsFiles/{}".format(BitBar.read_clipboard()))

    def clipboard_integrationsFiles_path_integration_containers(self):
        self.write_clipboard("/opt/files/shared/integrationsFiles/")

    def clipboard_integrationsFiles_path_integration_containers_from_file_name(self):
        self.write_clipboard("/opt/files/shared/integrationsFiles/{}".format(BitBar.read_clipboard()))

    def clipboard_integrationsFiles_path_service_container(self):
        self.write_clipboard("/opt/docker/data/shared/integrationsFiles/")

    def clipboard_integrationsFiles_path_service_container_from_file_name(self):
        self.write_clipboard("/opt/docker/data/shared/integrationsFiles/{}".format(BitBar.read_clipboard()))

    ############################################################################
    # LogicHub -> LogicHub Upgrades

    def logichub_upgrade_prep_verifications(self):
        """
        Upgrade Prep: Visual inspection

        :return:
        """
        self.copy_file_contents_to_clipboard(self.config.dir_supporting_scripts, "upgrade_prep-verify.sh")

    def logichub_upgrade_prep_backups(self):
        """
        Upgrade Prep: Backups

        :return:
        """
        self.copy_file_contents_to_clipboard(self.config.dir_supporting_scripts, "upgrade_prep-backups.sh")

    def logichub_upgrade_command_from_clipboard(self):
        """
        Upgrade Command (from milestone version in clipboard)

        :return:
        """
        version = self.read_clipboard()
        cmd = self.make_upgrade_command(version)
        self.write_clipboard(cmd)

    def logichub_upgrade_command_static(self):
        """
        Upgrade Command (static)

        :return:
        """
        cmd = self.make_upgrade_command()
        self.write_clipboard(cmd)

    def logichub_upgrade_command_from_clipboard_with_backup_script(self):
        """
        Upgrade Command with Backup Script (from milestone version in clipboard)

        :return:
        """
        version = self.read_clipboard()
        cmd = "{}; {}".format(self.make_backup_command(), self.make_upgrade_command(version))
        self.write_clipboard(cmd)

    def logichub_upgrade_command_static_with_backup_script(self):
        """
        Upgrade Command with Backup Script (static)

        :return:
        """
        cmd = "{}; {}".format(self.make_backup_command(), self.make_upgrade_command())
        self.write_clipboard(cmd)

    ############################################################################
    # Section:
    #   Networking
    ############################################################################

    def check_for_custom_networking_configs(self):
        if self.config.BitBar_networking:
            for _var in self.config.BitBar_networking.configs:
                if isinstance(self.config.BitBar_networking.configs[_var], dict):
                    if self.config.BitBar_networking.configs[_var].get("type") == "ssh":
                        self.ssh_tunnel_configs.append((self.config.BitBar_networking.configs[_var].get("name", _var), f"ssh_tunnel_custom_{_var}"))
                    elif self.config.BitBar_networking.configs[_var].get("type") == "redirect":
                        self.port_redirect_configs.append((self.config.BitBar_networking.configs[_var].get("name"), f"port_redirect_custom_{_var}"))

    ############################################################################
    # Networking -> Reset

    def do_terminate_tunnels(self, loopback_ip=None, loopback_port=None):
        """Terminate SSH tunnels"""

        # Get PID for all open SSH tunnels
        _cmd_result = _run_cli_command("ps -ef")
        pid_pattern = re.compile(r"^\s*\d+\s+(\d+)")
        specific_loopback = (loopback_ip.strip() if loopback_ip else "") + ":"
        if specific_loopback and loopback_port:
            specific_loopback += f"{loopback_port}:"
        tunnel_PIDs = {
            int(pid_pattern.findall(_line)[0]): _line
            for _line in _cmd_result.stdout.split('\n')
            if 'ssh' in _line and '-L' in _line and pid_pattern.match(_line) and specific_loopback in _line
        }

        # Check for an existing SSH tunnel. If none is found, abort, otherwise kill each process found.
        if not tunnel_PIDs:
            print("No existing SSH tunnels found")
            self.display_notification("No existing SSH tunnels found")
        else:
            # Validate sudo session
            do_prompt_for_sudo()
            for PID in tunnel_PIDs:
                tunnel = tunnel_PIDs[PID]
                local_host_info, remote_host_info = re.findall(r"[^\s:]+:\d+(?=:|\s)", tunnel)[0:2]
                _tmp_ssh_server = re.findall(r'-f +(\S+)', tunnel)[0]
                print(f"Killing {local_host_info} --> {remote_host_info} via {_tmp_ssh_server} (PID {PID})")
                _ = _run_cli_command(f'sudo kill -9 {PID}')
            self.display_notification("Tunnels terminated")

    def action_terminate_tunnels(self):
        self.do_terminate_tunnels()

    def do_terminate_port_redirection(self):
        print("Resetting port forwarding/redirection...")
        _run_cli_command('sudo pfctl -f /etc/pf.conf')
        output_msg = "Port redirection terminated"
        print(output_msg)
        self.display_notification(output_msg)

    def action_terminate_port_redirection(self):
        do_prompt_for_sudo()
        self.do_terminate_port_redirection()

    # ToDo Finish this or find an alternate way of helping with managing loopback aliases
    # Don't enable the following until this script is updated to take startup scripts into account
    def do_terminate_loopback_aliases(self):
        """
        from the old bash version:
            echo
            # When ready, add the following action to the bottom section:
            #echo "Terminate Loopback Aliases | bash='$0' param1=action_terminate_loopback_aliases terminal=true"
            #
            #    # Validate sudo session
            #    do_prompt_for_sudo
            #
            #    loopback_aliases=$(ifconfig -a | pcregrep -o 'inet \K127(?:\.\d+){3}' | pcregrep -v '127.0.0.1$' | sort -u)
            #    if [[ -z ${loopback_aliases} ]]; then
            #        echo "No loopback aliases found"
            #    else
            #        for loopback_alias in ${loopback_aliases}; do
            #            echo "Deleting loopback IP ${loopback_alias}"
            #            sudo ifconfig ${loopback_interface} ${loopback_alias} delete
            #        done
            #        display_notification "Loopback aliases terminated"
            #    fi
        """
        print("Feature not yet enabled")
        pass

    # ToDo Add an action for this function once it's operational
    def action_terminate_loopback_aliases(self):
        self.do_terminate_loopback_aliases()

    def action_terminate_all(self):
        # Validate sudo session
        do_prompt_for_sudo()

        print("\nTerminating all SSH tunnels tunnels...\n")
        self.do_terminate_tunnels()

        print("\nTerminating port redirection...\n")
        self.do_terminate_port_redirection()

        print("\nTerminating all loopback aliases...\n")
        self.do_terminate_loopback_aliases()

        print("\nDone. You may close the terminal.\n")
        sys.exit()

    ############################################################################
    # Networking -> Port Redirects

    def do_execute_port_redirect(self, source_address, source_port, target_address, target_port):
        self.do_verify_loopback_address(source_address)
        print_debug(f"Making alias to redirect {source_address}:{source_port} --> {target_address}:{target_port}")

        _command = f'echo "rdr pass inet proto tcp from any to {source_address} port {source_port} -> {target_address} port {target_port}" | sudo -p "sudo password: " pfctl -ef -'
        print()
        _ = _run_shell_command_with_pipes(_command)
        result = f"Port Redirection Enabled:\n\n{source_address}:{source_port} --> {target_address}:{target_port}"
        print(f"\n{result}\n")
        self.display_notification(result)

    def port_redirect_custom(self):
        def get_var(var_name):
            var = (config_dict.get(var_name) or "").strip()
            if not var:
                self.display_notification_error(f"variable {var_name} not found in redirect config", print_stderr=True)
            return var

        # """ Custom port redirection based on entries in logichub_tools.ini """
        config_name = re.sub('^port_redirect_custom_', '', sys.argv[1])
        config_dict = self.config.BitBar_networking.configs.get(config_name)
        if not config_dict:
            self.display_notification_error(f"Port redirect config [{config_name}] not found", print_stderr=True)

        source_address = get_var('source_address')
        source_port = get_var('source_port')
        target_address = get_var('target_address')
        target_port = get_var('target_port')
        optional_exit_message = config_dict.get("optional_exit_message")

        do_prompt_for_sudo()
        print(f"\nSetting up redirection for config \"{config_dict['name']}\"...\n")

        self.do_execute_port_redirect(source_address, source_port, target_address, target_port)

        print("Done. You may close the terminal.\n")
        if optional_exit_message:
            print(optional_exit_message.replace("\\n", "\n").replace("\\t", "\t"))

    ############################################################################
    # Networking -> SSH Tunnels

    def do_verify_loopback_address(self, loopback_ip, allow_all_loopback_ips=False):
        assert loopback_ip, "No loopback address provided"
        assert re.match(r"^127\..*", loopback_ip), f"Invalid loopback address ({loopback_ip})"
        if not allow_all_loopback_ips:
            assert loopback_ip != "127.0.0.1", "Custom loopback IP is required. As a precaution, this script requires a loopback IP other than 127.0.0.1"

        # Trim input, just in case
        loopback_ip = loopback_ip.strip()
        interfaces_output = _run_cli_command("ifconfig -a")

        # Make sure loopback alias exists; create if needed.
        if re.findall(rf"\b{loopback_ip}\b", interfaces_output.stdout):
            print_debug(f"Existing loopback alias {loopback_ip} found")
        else:
            print_debug(f"Loopback alias {loopback_ip} not found; creating")
            # Validate sudo session
            do_prompt_for_sudo()
            _ = _run_cli_command(f"sudo ifconfig {self.loopback_interface} alias ${loopback_ip}")

    def do_verify_ssh_tunnel_available(self, loopback_ip, loopback_port):
        print(f"Checking for existing tunnels {loopback_ip}:{loopback_port}...")
        self.do_terminate_tunnels(loopback_ip, loopback_port)

    def do_execute_ssh_tunnel(self, config_dict):
        """
        Execute an SSH tunnel based on a custom tunnel config from logichub_tools.ini

        :param config_dict: dict containing SSH tunnel parameters
        :return:
        """
        # Validate sudo session
        do_prompt_for_sudo()

        ssh_config_name = config_dict.get("name")
        remote_address = config_dict.get("remote_ip")
        remote_port = config_dict.get("remote_port")
        local_address = config_dict.get("local_address")
        local_port = config_dict.get("local_port") or remote_port
        ssh_server_address = config_dict.get("ssh_server")
        ssh_server_port = config_dict.get("ssh_port") or 22
        ssh_user = config_dict.get("ssh_user") or self.config.local_user
        ssh_key = config_dict.get("ssh_key") or self.config.default_ssh_key
        ssh_options = config_dict.get("ssh_options", "").strip()

        # Ensure that required parameters are present
        assert ssh_config_name, "Error: SSH config must be given a name"
        assert ssh_server_address, "Error: SSH server address not provided"
        assert remote_address, "Error: Remote address for SSH tunnel not provided"
        assert remote_port, "Error: Remote port for SSH tunnel not provided"
        assert local_address, "Error: Loopback address not provided"
        assert local_port, "Error: Loopback port not provided"

        # If the SSH server address is a loopback IP (like when tunneling over another tunnel, such as Bomgar tunnel jumps)
        # Make sure the server port is not left at 22. Otherwise a tunnel to your own machine will be created and won't work.
        assert ssh_server_port != 22 or not re.match(r'^127\..*', ssh_server_address), \
            "Error: SSH server is a loopback IP, and the port is left at 22. This will create a tunnel to your own machine and won't work!"

        # Sanitize loopback address input, and verify that the address actually exists
        self.do_verify_loopback_address(local_address)

        # Kill existing tunnel if one is up already
        self.do_verify_ssh_tunnel_available(local_address, local_port)

        # Set default options (which includes skipping known_hosts)
        default_ssh_options = f"-i {ssh_key} -o StrictHostKeyChecking=no"

        # If ssh_options includes a specific ssh key already, then no key will be added
        if not ssh_options:
            # If SSH options were not provided, just point to the default SSH key
            ssh_options = default_ssh_options
        elif "-i" not in ssh_options:
            # If options were provided but no key was included, append the SSH key to use
            ssh_options = f"-i {ssh_key} {ssh_options}"

        # Initiate reverse SSH tunnel
        print(f"Redirecting for {ssh_config_name}\n")
        print(f"From Local:\n\t{local_address}:{local_port}\n")
        print(f"To Remote:\n\t{remote_address}:{remote_port}\n\n")

        # Define the SSH command
        #   * must use sudo in case the local port is below 1024
        ssh_command = f"sudo ssh {ssh_options} -Y -L {local_address}:{local_port}:{remote_address}:{remote_port} -N -f {ssh_user}@{ssh_server_address} -p {ssh_server_port}"

        print(f"Executing command:\n\n    {ssh_command}\n")

        # Run SSH command
        # Bash version for reference: eval "${ssh_command}"
        _ = _run_cli_command(ssh_command, capture_output=False, timeout=60)

        print(f"\nSSH tunnel complete\n\n")

    def ssh_tunnel_custom(self):
        """ Custom SSH tunnel based on entries in logichub_tools.ini """
        config_name = re.sub('^ssh_tunnel_custom_', '', sys.argv[1])
        if not self.config.BitBar_networking.configs.get(config_name):
            self.display_notification_error(f"SSH tunnel config [{config_name}] not found", print_stderr=True)
        tunnel_config = self.config.BitBar_networking.configs[config_name]
        self.do_execute_ssh_tunnel(tunnel_config)

    ############################################################################
    # Section:
    #   TECH
    ############################################################################

    ############################################################################
    # TECH -> JSON

    @staticmethod
    def do_fix_json(json_str):
        def run_fix(obj, step_count=None):
            step_count = 0 if step_count is None else step_count + 1
            if type(obj) is bytes:
                raise TypeError("JSON input cannot be bytes")
            if type(obj) is str:
                try:
                    obj = json.loads(obj)
                except (TypeError, json.JSONDecodeError) as err:
                    if step_count:
                        return obj
                    else:
                        raise Exception("Initial input could not be parsed as valid JSON")

            # Loop through all entries in case there are nested dicts or strings.
            if type(obj) in (list, tuple):
                obj = [run_fix(entry, step_count=step_count) for entry in obj]
            elif isinstance(obj, dict):
                obj = {k: run_fix(obj[k], step_count=step_count) for k in obj.keys()}
            return obj

        return run_fix(json_str)

    def json_notify_and_exit_when_invalid(self):
        """
        Reusable script to validate that what is in the clipboard is valid JSON,
        and raise an alert and exit if it is not.

        :return:
        """
        _input = BitBar.read_clipboard()
        try:
            json_dict = json.loads(_input, strict=False)
        except ValueError:
            json_dict = None

        if not json_dict or not isinstance(json_dict, (dict, list)):
            self.display_notification_error(self.notification_json_invalid, self.title_json)
            sys.exit(1)
        else:
            return json_dict

    def json_validate(self):
        json_loaded = self.json_notify_and_exit_when_invalid()
        if isinstance(json_loaded, dict):
            self.display_notification("Valid JSON, type: dict")
        else:
            self.display_notification(f"Valid JSON, type: {type(json_loaded).__name__}")

    def json_format(self):
        json_loaded = self.json_notify_and_exit_when_invalid()
        self.write_clipboard(json.dumps(json_loaded, ensure_ascii=False, indent=2))

    def json_compact(self):
        """ Placeholder: JSON Compact """
        json_loaded = self.json_notify_and_exit_when_invalid()
        self.write_clipboard(json.dumps(json_loaded, ensure_ascii=False, separators=(',', ':')))

    def action_json_fix(self):
        """ Placeholder: JSON Compact """
        # If there are newlines in the clipboard, assume that it is formatted JSON
        # If no newlines, then return compact JSON
        is_formatted = '\n' in BitBar.read_clipboard()
        json_loaded = self.json_notify_and_exit_when_invalid()
        fixed_json = self.do_fix_json(json_loaded)
        if is_formatted:
            self.write_clipboard(json.dumps(fixed_json, ensure_ascii=False, indent=2))
        else:
            self.write_clipboard(json.dumps(fixed_json, ensure_ascii=False, separators=(',', ':')))

    ############################################################################
    # TECH -> Link Makers

    def make_link(self, url: str, open_url: bool = False, override_clipboard=None):
        """
        Standardized link making. Provide a URL with '{}' in place of the
        desired location for clipboard text. If open_url is enabled, the
        clipboard will be left intact, and the URL will be opened in the user's
        default browser.

        :param url:
        :param open_url:
        :param override_clipboard:
        :return:
        """
        _input = override_clipboard if override_clipboard else BitBar.read_clipboard()
        url = url.replace(r'{}', _input)
        if open_url is True:
            subprocess.call(["open", url])
        else:
            self.write_clipboard(url)

    def add_default_jira_project_when_needed(self):
        default_prefix = self.config.jira_default_prefix
        jira_issue = BitBar.read_clipboard().upper()
        if re.match(r"^\d+$", jira_issue):
            jira_issue = f"{default_prefix}-{jira_issue}"
        return jira_issue

    def make_link_jira_and_open(self):
        """
        Jira: Open Link from ID

        :return:
        """
        jira_issue = self.add_default_jira_project_when_needed()
        self.make_link(self.url_jira, override_clipboard=jira_issue, open_url=True)

    def make_link_jira(self):
        """
        Jira: Make Link from ID

        :return:
        """
        jira_issue = self.add_default_jira_project_when_needed()
        self.make_link(self.url_jira, override_clipboard=jira_issue)

    def make_link_uws_and_open(self):
        """
        Jira: UWS: Open link from Windows event ID

        :return:
        """
        self.make_link(self.url_uws, open_url=True)

    def make_link_uws(self):
        """
        Jira: UWS: Make link from Windows event ID

        :return:
        """
        self.make_link(self.url_uws)

    def make_link_nmap_script_and_open(self):
        """
        Nmap: Open link to script documentation

        :return:
        """
        self.make_link(self.url_nmap, open_url=True)

    def make_link_nmap_script(self):
        """
        Nmap: Make link to script documentation

        :return:
        """
        self.make_link(self.url_nmap)

    ############################################################################
    # TECH -> Shell Commands (general)

    # Visual Mode, Permanent
    def shell_vim_visual_mode_disable_permanently(self):
        """
        vim: visual mode - disable permanently

        :return:
        """
        self.write_clipboard(r"""if [[ -f ~/.vimrc ]]; then sed -E -i".$(date +'%Y%m%d_%H%M%S').bak" '/^set mouse/d' ~/.vimrc; else touch ~/.vimrc; fi ; echo 'set mouse-=a' >> ~/.vimrc""")

    def shell_vim_visual_mode_enable_permanently(self):
        """
        vim: visual mode - enable permanently

        :return:
        """
        self.write_clipboard(r"""if [[ -f ~/.vimrc ]]; then sed -E -i".$(date +'%Y%m%d_%H%M%S').bak" '/^set mouse/d' ~/.vimrc; else touch ~/.vimrc; fi ; echo 'set mouse=a' >> ~/.vimrc""")

    # Visual Mode, Temporary (within an active session)
    def shell_vim_visual_mode_disable_within_session(self):
        """
        vim: visual mode - disable within a session

        :return:
        """
        self.write_clipboard(r""":set mouse-=a""")

    def shell_vim_visual_mode_enable_within_session(self):
        """
        vim: visual mode - enable within a session

        :return:
        """
        self.write_clipboard(r""":set mouse=a""")

    # Show Line Numbers, Permanent
    def shell_vim_line_numbers_enable_permanently(self):
        """
        vim: line numbers - enable permanently

        :return:
        """
        self.write_clipboard(r"""if [[ -f ~/.vimrc ]]; then sed -E -i".$(date +'%Y%m%d_%H%M%S').bak" '/^set nonumber/d' ~/.vimrc; else touch ~/.vimrc; fi ; echo 'set number' >> ~/.vimrc""")

    def shell_vim_line_numbers_disable_permanently(self):
        """
        vim: line numbers - disable permanently

        :return:
        """
        self.write_clipboard(r"""if [[ -f ~/.vimrc ]]; then sed -E -i".$(date +'%Y%m%d_%H%M%S').bak" '/^set number/d' ~/.vimrc; else touch ~/.vimrc; fi ; echo 'set nonumber' >> ~/.vimrc""")

    # Show Line Numbers, Temporary (within an active session)
    def shell_vim_line_numbers_enable_within_session(self):
        """
        vim: line numbers - enable within a session

        :return:
        """
        self.write_clipboard(r""":set number""")

    def shell_vim_line_numbers_disable_within_session(self):
        """
        vim: line numbers - disable within a session

        :return:
        """
        self.write_clipboard(r""":set nonumber""")

    def shell_vim_set_both_permanently(self):
        """
        vim: Set both permanently

        :return:
        """
        self.write_clipboard(r"""if [[ -f ~/.vimrc ]]; then sed -E -i".$(date +'%Y%m%d_%H%M%S').bak" '/^ *set *((no)?number|mouse)/d' ~/.vimrc; fi; printf "set mouse-=a\nset number\n" >> ~/.vimrc""")

    ############################################################################
    # TECH -> Text Editing

    def text_make_uppercase(self):
        """
        Text to Uppercase

        :return:
        """
        self.write_clipboard(self.read_clipboard(trim_input=False).upper())

    def text_make_lowercase(self):
        """
        Text to Lowercase

        :return:
        """
        self.write_clipboard(self.read_clipboard(trim_input=False).lower())

    def text_trim_string(self):
        """
        Trim Text in Clipboard

        :return:
        """
        self.write_clipboard(self.read_clipboard(trim_input=False).strip())

    def text_remove_formatting(self):
        """
        Remove Text Formatting
        (Merely copies text from clipboard back into clipboard, thus removing text formatting)

        :return:
        """
        self.write_clipboard(self.read_clipboard(trim_input=False))

    def execute(self, action):
        if not action:
            self.print_bitbar_menu_output()
        else:
            try:
                self.action_list[action].action()
            except KeyError:
                raise Exception("Not a valid action")


def main():
    requested_action = None if len(sys.argv) == 1 else sys.argv[1]
    bar = BitBar()
    bar.execute(requested_action)


if __name__ == "__main__":
    main()
