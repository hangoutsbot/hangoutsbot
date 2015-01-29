import sys, json, asyncio, logging, os

import hangups
from hangups.ui.utils import get_conv_name

from utils import text_to_segments

from inspect import getmembers, isfunction

class CommandDispatcher(object):
    """Register commands and run them"""
    def __init__(self):
        self.commands = {}
        self.unknown_command = None

    @asyncio.coroutine
    def run(self, bot, event, *args, **kwds):
        """Run command"""
        try:
            func = self.commands[args[0]]
        except KeyError:
            if self.unknown_command:
                func = self.unknown_command
            else:
                raise

        # Automatically wrap command function in coroutine
        # (so we don't have to write @asyncio.coroutine decorator before every command function)
        func = asyncio.coroutine(func)

        args = list(args[1:])

        try:
            yield from func(bot, event, *args, **kwds)
        except Exception as e:
            print(e)
            raise

    def register(self, func):
        """Decorator for registering command"""
        self.commands[func.__name__] = func
        return func

    def register_unknown(self, func):
        """Decorator for registering unknown command"""
        self.unknown_command = func
        return func

# CommandDispatcher singleton
command = CommandDispatcher()

@command.register
def help(bot, event, cmd=None, *args):
    """list supported commands"""
    if not cmd:
        segments = [hangups.ChatMessageSegment('Supported commands:', is_bold=True),
                    hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                    hangups.ChatMessageSegment(', '.join(sorted(command.commands.keys())))]
    else:
        try:
            command_fn = command.commands[cmd]
            segments = [hangups.ChatMessageSegment('{}:'.format(cmd), is_bold=True),
                        hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
            segments.extend(text_to_segments(command_fn.__doc__))
        except KeyError:
            yield from command.unknown_command(bot, event)
            return

    bot.send_message_segments(event.conv, segments)


@command.register
def ping(bot, event, *args):
    """reply to a ping"""
    bot.send_message(event.conv, 'pong')

@command.register_unknown
def unknown_command(bot, event, *args):
    """handle unknown commands"""
    bot.send_message(event.conv,
                     '{}: unknown command'.format(event.user.full_name))


# load in all plugins.*
plugin_list = ["default", "mentions", "lottery", "lookup", "easteregg", "chance"]
for module in plugin_list: 
    module_path = "plugins.{}".format(module)
    exec("import {}".format(module_path))
    functions_list = [o for o in getmembers(sys.modules[module_path], isfunction)]
    for function in functions_list:
        command.register(function[1])
        print("registered function '{}' from {}".format(function[0], module_path))