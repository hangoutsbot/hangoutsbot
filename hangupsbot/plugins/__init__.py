import os
import sys
import logging

from inspect import getmembers, isfunction
from commands import command

class tracker:
    def __init__(self):
        self.list = []
        self._current = None

    def reset(self):
        self._current = {
            "commands": {
                "admin": [],
                "user": [],
                "all": None
            },
            "handlers": [],
            "metadata": None
        }

    def start(self, metadata):
        self.reset()
        self._current["metadata"] = metadata

    def current(self):
        self._current["commands"]["all"] = list(
            set(self._current["commands"]["admin"] +
                self._current["commands"]["user"]))
        return self._current

    def end(self):
        self.list.append(self.current())

    def register_command(self, type, command_names):
        """call during plugin init to register commands"""
        self._current["commands"][type].extend(command_names)
        self._current["commands"][type] = list(set(self._current["commands"][type]))

tracking = tracker()

def register_user_command(command_names):
    """call during plugin init to register user commands"""
    if not isinstance(command_names, list):
        command_names = [command_names]
    tracking.register_command("user", command_names)

def register_admin_command(command_names):
    """call during plugin init to register admin commands"""
    if not isinstance(command_names, list):
        command_names = [command_names]
    tracking.register_command("admin", command_names)
    command.admin_commands.extend(command_names)

def load(bot, command_dispatcher):
    plugin_list = bot.get_config_option('plugins')
    if plugin_list is None:
        print(_("HangupsBot: config.plugins is not defined, using ALL"))
        plugin_path = os.path.dirname(os.path.realpath(sys.argv[0])) + os.sep + "plugins"
        plugin_list = [ os.path.splitext(f)[0]  # take only base name (no extension)...
            for f in os.listdir(plugin_path)    # ...by iterating through each node in the plugin_path...
                if not f.startswith(("_", ".")) and ( # ...that does not start with _ .
                    (os.path.isfile(os.path.join(plugin_path, f))
                        and f.endswith(".py")) or # ...and must end with .py
                    (os.path.isdir(os.path.join(plugin_path, f)))
                )]

    for module in plugin_list:
        module_path = "plugins.{}".format(module)

        tracking.start({ "module": module, "module.path": module_path })

        try:
            exec("import {}".format(module_path))
        except Exception as e:
            message = "{} @ {}".format(e, module_path)
            print(_("EXCEPTION during plugin import: {}").format(message))
            logging.exception(message)
            continue

        print(_("plugin: {}").format(module))
        public_functions = [o for o in getmembers(sys.modules[module_path], isfunction)]

        candidate_commands = []

        """
        pass 1: run _initialise()/_initialize() and filter out "hidden" functions

        legacy notice:
        older plugins will return a list of user-available functions via _initialise/_initialize().
        this LEGACY behaviour will continue to be supported. however, it is HIGHLY RECOMMENDED to
        use register_user_command(<LIST command_names>) and register_admin_command(<LIST command_names>)
        for better security
        """
        available_commands = False # default: ALL
        try:
            for function_name, the_function in public_functions:
                if function_name ==  "_initialise" or function_name ==  "_initialize":
                    try:
                        _return = the_function(bot._handlers, bot)
                    except TypeError as e:
                        # implement legacy support for plugins that don't support the bot reference
                        _return = the_function(bot._handlers)
                    if type(_return) is list:
                        available_commands = _return
                elif function_name.startswith("_"):
                    pass
                else:
                    candidate_commands.append((function_name, the_function))
            if available_commands is False:
                # implicit init, legacy support: assume all candidate_commands are user-available
                register_user_command([function_name for function_name, function in candidate_commands])
            elif available_commands is []:
                # explicit init, no user-available commands
                pass
            else:
                # explicit init, legacy support: _initialise() returned user-available commands
                register_user_command(available_commands)
        except Exception as e:
            message = "{} @ {}".format(e, module_path)
            print(_("EXCEPTION during plugin init: {}").format(message))
            logging.exception(message)
            continue # skip this, attempt next plugin

        """
        pass 2: register filtered functions
        """
        plugin_tracking = tracking.current()
        explicit_admin_commands = plugin_tracking["commands"]["admin"]
        all_commands = plugin_tracking["commands"]["all"]
        registered_commands = []
        for function_name, the_function in candidate_commands:
            if function_name in all_commands:
                command_dispatcher.register(the_function)
                text_function_name = function_name
                if function_name in explicit_admin_commands:
                    text_function_name = "*" + text_function_name
                registered_commands.append(text_function_name)

        if registered_commands:
            print(_("added: {}").format(", ".join(registered_commands)))
