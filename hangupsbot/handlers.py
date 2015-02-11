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

        self._current_plugin = {}

        self.plugin_registered_admin_commands = []

        self.pluggables = { "message":[], "membership":[], "rename":[], "sending":[] }

    def plugin_preinit_stats(self):
        """ 
        hacky implementation for tracking commands a plugin registers
        manually called by Hangupsbot._load_plugins() at start of each plugin load
        """
        self._current_plugin = {
            "commands": {
                "admin": [],
                "user": []
            }
        }

    def plugin_get_stats(self):
        self._current_plugin["commands"]["all"] = list(set(self._current_plugin["commands"]["admin"] + 
                                                           self._current_plugin["commands"]["user"]))
        return self._current_plugin

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
        self.plugin_registered_admin_commands.extend(command_names)


    def register_handler(self, function, type="message"):
        """call during plugin init to register a handler for a specific bot event"""
        # print('register_handler(): "{}" registered for "{}"'.format(function.__name__, type))
        self.pluggables[type].append(function)

    def get_admin_commands(self, conversation_id):
        # get list of commands that are admin-only, set in config.json OR plugin-registered
        commands_admin_list = self.bot.get_config_suboption(conversation_id, 'commands_admin')
        if not commands_admin_list:
            commands_admin_list = []
        commands_admin_list = commands_admin_list + self.plugin_registered_admin_commands
        return commands_admin_list

    @asyncio.coroutine
    def handle_chat_message(self, event):
        """Handle conversation event"""
        if logging.root.level == logging.DEBUG:
            event.print_debug()

        if not event.user.is_self and event.text:
            # handlers from plugins
            if "message" in self.pluggables:
                for function in self.pluggables["message"]:
                    try:
                        yield from function(self.bot, event, command)
                    except:
                        message = "pluggables.message.{}".format(function.__name__)
                        print("EXCEPTION in " + format(message))
                        logging.exception(message)

            # Run command
            yield from self.handle_command(event)

    @asyncio.coroutine
    def handle_command(self, event):
        """Handle command messages"""
        # Test if command handling is enabled
        if not self.bot.get_config_suboption(event.conv_id, 'commands_enabled'):
            return

        if event.text.split()[0].lower() != self.bot_command:
            return

        # Parse message
        event.text = event.text.replace(u'\xa0', u' ') # convert non-breaking space in Latin1 (ISO 8859-1)
        line_args = shlex.split(event.text, posix=False)

        # Test if command length is sufficient
        if len(line_args) < 2:
            self.bot.send_message(event.conv, '{}: missing parameter(s)'.format(event.user.full_name))
            return

        commands_admin_list = self.get_admin_commands(event.conv_id)

        if commands_admin_list and line_args[1].lower() in commands_admin_list:
            admins_list = self.bot.get_config_suboption(event.conv_id, 'admins')
            # verify user is an admin
            if event.user_id.chat_id not in admins_list:
                self.bot.send_message(event.conv, '{}: Can\'t do that.'.format(event.user.full_name))
                return

        # Run command
        yield from asyncio.sleep(0.2)
        yield from command.run(self.bot, event, *line_args[1:])

    @asyncio.coroutine
    def handle_chat_membership(self, event):
        """Handle conversation membership change"""

        # handlers from plugins
        if "membership" in self.pluggables:
            for function in self.pluggables["membership"]:
                try:
                    yield from function(self.bot, event, command)
                except:
                    message = "pluggables.membership.{}".format(function.__name__)
                    print("EXCEPTION in " + format(message))
                    logging.exception(message)

    @asyncio.coroutine
    def handle_chat_rename(self, event):
        # handlers from plugins
        if "rename" in self.pluggables:
            for function in self.pluggables["rename"]:
                try:
                    yield from function(self.bot, event, command)
                except:
                    message = "pluggables.rename.{}".format(function.__name__)
                    print("EXCEPTION in " + format(message))
                    logging.exception(message)
