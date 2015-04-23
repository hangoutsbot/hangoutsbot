import os
import sys
import logging
import inspect

from inspect import getmembers, isfunction
from commands import command
import handlers

class tracker:
    def __init__(self):
        self.bot = None
        self.list = []
        self._current = None

    def set_bot(self, bot):
        self.bot = bot

    def reset(self):
        self._current = {
            "commands": {
                "admin": [],
                "user": [],
                "all": None
            },
            "handlers": [],
            "shared": [],
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

    def register_handler(self, function, type, priority):
        self._current["handlers"].append((function, type, priority))

    def register_shared(self, id, objectref, forgiving):
        self._current["shared"].append((id, objectref, forgiving))


tracking = tracker()

"""helpers"""

def register_user_command(command_names):
    """user command registration"""
    if not isinstance(command_names, list):
        command_names = [command_names]
    tracking.register_command("user", command_names)

def register_admin_command(command_names):
    """admin command registration, overrides user command registration"""
    if not isinstance(command_names, list):
        command_names = [command_names]
    tracking.register_command("admin", command_names)

def register_handler(function, type="message", priority=50):
    """register external handler"""
    bot_handlers = tracking.bot._handlers
    bot_handlers.register_handler(function, type, priority)

def register_shared(id, objectref, forgiving=True):
    """register shared object"""
    bot = tracking.bot
    bot.register_shared(id, objectref, forgiving=forgiving)

"""plugin loader"""

def load(bot, command_dispatcher):
    tracking.set_bot(bot)
    command_dispatcher.set_tracking(tracking)

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

        """pass 1: run optional callable: _initialise, _initialize
        * performs house-keeping tasks (e.g. migration, tear-up, pre-init, etc)
        * registers user and/or admin commands
        """
        available_commands = False # default: ALL
        try:
            for function_name, the_function in public_functions:
                if function_name ==  "_initialise" or function_name ==  "_initialize":
                    """accepted function signatures:
                    CURRENT
                    version >= 2.4 | function()
                    version >= 2.4 | function(bot) - parameter must be named "bot"
                    LEGACY
                    version <= 2.4 | function(handlers, bot)
                    ancient        | function(handlers)
                    """
                    _expected = list(inspect.signature(the_function).parameters)
                    if len(_expected) == 0:
                        the_function()
                        _return = []
                    elif len(_expected) == 1 and _expected[0] == "bot":
                        the_function(bot)
                        _return = []
                    else:
                        try:
                            # legacy support, pre-2.4
                            _return = the_function(bot._handlers, bot)
                        except TypeError as e:
                            # legacy support, ancient plugins
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
        tracking.current() and the CommandDispatcher registers might be out of sync if a 
        combination of decorators and register_user_command/register_admin_command is used since
        decorators execute immediately upon import
        """
        plugin_tracking = tracking.current()
        explicit_admin_commands = plugin_tracking["commands"]["admin"]
        all_commands = plugin_tracking["commands"]["all"]
        registered_commands = []
        for function_name, the_function in candidate_commands:
            if function_name in all_commands:
                is_admin = False
                text_function_name = function_name
                if function_name in explicit_admin_commands:
                    is_admin = True
                    text_function_name = "*" + text_function_name
                command_dispatcher.register(the_function, admin=is_admin)
                registered_commands.append(text_function_name)

        if registered_commands:
            print(_("added: {}").format(", ".join(registered_commands)))

        tracking.end()


@command.register(admin=True)
def plugininfo(bot, event, *args):
    """dumps plugin information"""
    lines = []
    for plugin in tracking.list:
        if len(args) == 0 or args[0] in plugin["metadata"]["module"]:
            print("{}".format(plugin))
            lines.append("<b>{}</b>".format(plugin["metadata"]["module.path"]))
            """admin commands"""
            if len(plugin["commands"]["admin"]) > 0:
                lines.append("<i>admin commands:</i> {}".format(", ".join(plugin["commands"]["admin"])))
            """user-only commands"""
            user_only_commands = list(set(plugin["commands"]["user"]) - set(plugin["commands"]["admin"]))
            if len(user_only_commands) > 0:
                lines.append("<i>user commands:</i> {}".format(", ".join(user_only_commands)))
            """handlers"""
            if len(plugin["handlers"]) > 0:
                lines.append("<i>handlers:</i>" + ", ".join([ "{} ({}, p={})".format(f[0].__name__, f[1], str(f[2])) for f in plugin["handlers"]]))
            """shared"""
            if len(plugin["shared"]) > 0:
                lines.append("<i>shared:</i>" + ", ".join([f[1].__name__ for f in plugin["shared"]]))
            lines.append("")
    bot.send_html_to_conversation(event.conv_id, "<br />".join(lines))