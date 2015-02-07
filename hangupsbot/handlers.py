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

        self.pluggables = { "message":[], "membership":[], "rename":[], "sending":[] }


    def register_handler(self, function, type="message"):
        """plugins call this to preload any handlers to be used by EventHandler"""
        print('register_handler(): "{}" registered for "{}"'.format(function.__name__, type))
        self.pluggables[type].append(function)

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

        # Test if user has permissions for running command
        commands_admin_list = self.bot.get_config_suboption(event.conv_id, 'commands_admin')
        if commands_admin_list and line_args[1].lower() in commands_admin_list:
            admins_list = self.bot.get_config_suboption(event.conv_id, 'admins')
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
