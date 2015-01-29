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

        self._handlers = []

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

    def register_handler(self, function):
        """plugins call this to preload any handlers to be used by MessageHandler"""
        self._handlers.append(function)

    def attach_extra_handlers(self, MessageHandler):
        """called by MessageHandler to get all handlers loaded by plugins"""
        MessageHandler._extra_handlers = self._handlers

    def initialise_plugins(self, plugin_list):
        for module in plugin_list: 
            module_path = "plugins.{}".format(module)
            exec("import {}".format(module_path))
            functions_list = [o for o in getmembers(sys.modules[module_path], isfunction)]

            filter_commands = False
            found_commands = []

            """
            pass 1: run _initialise()/_initialize() and filter out "hidden" functions
            _initialise()/_initialize() can return a list of functions available to the user
                use the return value when importing functions from external libraries
            """
            for function in functions_list:
                function_name = function[0]
                if function_name ==  "_initialise" or function_name ==  "_initialize":
                    _return = function[1](self)
                    if type(_return) is list:
                        print("manual introspection: {} implements {}".format(module_path, _return))
                        filter_commands = _return
                elif function_name.startswith("_"):
                    pass
                else:
                    found_commands.append(function)

            """pass 2: register filtered functions"""
            for function in found_commands:
                function_name = function[0]
                if filter_commands is False or function_name in filter_commands:
                    self.register(function[1])
                    print("registered function '{}' from {}".format(function_name, module_path))


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