import logging, shlex, asyncio

import hangups

import re, time

from commands import command

from hangups.ui.utils import get_conv_name

class EventHandler(object):
    """Handle Hangups conversation events"""

    def __init__(self, bot, bot_command='/bot'):
        self.bot = bot
        self.bot_command = bot_command

        self.explicit_admin_commands = [] # plugins can force some commands to be admin-only via register_admin_command()

        self.pluggables = { "message":[], "membership":[], "rename":[], "sending":[] }

    def plugin_preinit_stats(self, plugin_metadata):
        """ 
        hacky implementation for tracking commands a plugin registers
        called automatically by Hangupsbot._load_plugins() at start of each plugin load
        """
        self._current_plugin = {
            "commands": {
                "admin": [],
                "user": []
            },
            "metadata": plugin_metadata
        }

    def plugin_get_stats(self):
        """called automatically by Hangupsbot._load_plugins()"""
        self._current_plugin["commands"]["all"] = list(
            set(self._current_plugin["commands"]["admin"] + 
                self._current_plugin["commands"]["user"]))
        return self._current_plugin

    def all_plugins_loaded(self):
        """called automatically by HangupsBot._load_plugins() after everything is done.
        used to finish plugins loading and to do any house-keeping
        """
        for type in self.pluggables:
            self.pluggables[type].sort(key=lambda tup: tup[1])

    def _plugin_register_command(self, type, command_names):
        """call during plugin init to register commands"""
        self._current_plugin["commands"][type].extend(command_names)
        self._current_plugin["commands"][type] = list(set(self._current_plugin["commands"][type]))

    def register_user_command(self, command_names):
        """call during plugin init to register user commands"""
        if not isinstance(command_names, list):
            command_names = [command_names] # wrap into a list for consistent processing
        self._plugin_register_command("user", command_names)

    def register_admin_command(self, command_names):
        """call during plugin init to register admin commands"""
        if not isinstance(command_names, list):
            command_names = [command_names] # wrap into a list for consistent processing
        self._plugin_register_command("admin", command_names)
        self.explicit_admin_commands.extend(command_names)

    def register_object(self, id, objectref, forgiving=True):
        """registers a shared object into bot.shared"""
        try:
            self.bot.register_shared(id, objectref)
        except RuntimeError:
            if forgiving:
                print("register_object(): {} already registered".format(id))
            else:
                raise

    def register_handler(self, function, type="message", priority=50):
        """call during plugin init to register a handler for a specific bot event"""
        self.pluggables[type].append((function, priority, self._current_plugin["metadata"]))

    def get_admin_commands(self, conversation_id):
        # get list of commands that are admin-only, set in config.json OR plugin-registered
        commands_admin_list = self.bot.get_config_suboption(conversation_id, 'commands_admin')
        if not commands_admin_list:
            commands_admin_list = []
        commands_admin_list = list(set(commands_admin_list + self.explicit_admin_commands))
        return commands_admin_list

    @asyncio.coroutine
    def handle_chat_message(self, event):
        """Handle conversation event"""
        if logging.root.level == logging.DEBUG:
            event.print_debug()

        if not event.user.is_self and event.text:
            # handlers from plugins
            yield from self.run_pluggable_omnibus("message", self.bot, event, command)

            # Run command
            yield from self.handle_command(event)

    @asyncio.coroutine
    def handle_command(self, event):
        """Handle command messages"""

        # verify user is an admin
        admins_list = self.bot.get_config_suboption(event.conv_id, 'admins')
        initiator_is_admin = False
        if event.user_id.chat_id in admins_list:
            initiator_is_admin = True

        # Test if command handling is enabled
        # note: admins always bypass this check
        if not initiator_is_admin:
            if not self.bot.get_config_suboption(event.conv_id, 'commands_enabled'):
                return

        if not isinstance(self.bot_command, list):
            # always a list
            self.bot_command = [self.bot_command]

        if not event.text.split()[0].lower() in self.bot_command:
            return

        # Parse message
        event.text = event.text.replace(u'\xa0', u' ') # convert non-breaking space in Latin1 (ISO 8859-1)
        line_args = shlex.split(event.text, posix=False)

        # Test if command length is sufficient
        if len(line_args) < 2:
            self.bot.send_message(event.conv, '{}: missing parameter(s)'.format(event.user.full_name))
            return

        # only admins can run admin commands
        commands_admin_list = self.get_admin_commands(event.conv_id)
        if commands_admin_list and line_args[1].lower() in commands_admin_list:
            if not initiator_is_admin:
                self.bot.send_message(event.conv, '{}: Can\'t do that.'.format(event.user.full_name))
                return

        # Run command
        yield from asyncio.sleep(0.2)
        yield from command.run(self.bot, event, *line_args[1:])

    @asyncio.coroutine
    def handle_chat_membership(self, event):
        """handle conversation membership change"""
        yield from self.run_pluggable_omnibus("membership", self.bot, event, command)

    @asyncio.coroutine
    def handle_chat_rename(self, event):
        """handle conversation name change"""
        yield from self.run_pluggable_omnibus("rename", self.bot, event, command)


    @asyncio.coroutine
    def run_pluggable_omnibus(self, name, *args, **kwargs):
        if name in self.pluggables:
            try:
                for function, priority, plugin_metadata in self.pluggables[name]:
                    message = ["{}: {}.{}".format(
                                name, 
                                plugin_metadata[1],
                                function.__name__)]

                    try:
                        if asyncio.iscoroutinefunction(function):
                            message.append("coroutine")
                            print(" : ".join(message))
                            yield from function(*args, **kwargs)
                        else:
                            message.append("function")
                            print(" : ".join(message))
                            function(*args, **kwargs)
                    except self.bot.Exceptions.SuppressHandler:
                        # skip this pluggable, continue with next
                        message.append("SuppressHandler")
                        print(" : ".join(message))
                        pass
                    except (self.bot.Exceptions.SuppressEventHandling, 
                            self.bot.Exceptions.SuppressAllHandlers):
                        # skip all pluggables, decide whether to handle event at next level
                        raise
                    except:
                        message = " : ".join(message)
                        print("EXCEPTION in " + format(message))
                        logging.exception(message)

            except self.bot.Exceptions.SuppressAllHandlers:
                # skip all other pluggables, but let the event continue
                message.append("SuppressAllHandlers")
                print(" : ".join(message))
                pass
            except:
                raise