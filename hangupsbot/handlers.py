import logging
import shlex
import asyncio
import inspect

import hangups
from hangups.ui.utils import get_conv_name

import plugins
from commands import command


class EventHandler:
    """Handle Hangups conversation events"""

    def __init__(self, bot, bot_command='/bot'):
        self.bot = bot
        self.bot_command = bot_command

        self.pluggables = { "allmessages": [], "message":[], "membership":[], "rename":[], "sending":[] }

    def register_handler(self, function, type="message", priority=50):
        """registers extra event handlers"""
        if type in ["allmessages", "message", "membership", "rename"]:
            if not asyncio.iscoroutine(function):
                # transparently convert into coroutine
                function = asyncio.coroutine(function)
        elif type in ["sending"]:
            if asyncio.iscoroutine(function):
                raise RuntimeError("{} handler cannot be a coroutine".format(type))
        else:
            raise ValueError("unknown event type for handler: {}".format(type))

        current_plugin = plugins.tracking.current()
        self.pluggables[type].append((function, priority, current_plugin["metadata"]))
        self.pluggables[type].sort(key=lambda tup: tup[1])

        plugins.tracking.register_handler(function, type, priority)

    """legacy helpers, pre-2.4"""

    def register_object(self, id, objectref, forgiving=True):
        """registers a shared object into bot.shared
        historically, this function was more lenient than the actual bot function it calls
        """
        print("LEGACY handlers.register_object(): use plugins.register_shared")
        self.bot.register_shared(id, objectref, forgiving=forgiving)

    def register_user_command(self, command_names):
        print("LEGACY handlers.register_user_command(): use plugins.register_user_command")
        plugins.register_user_command(command_names)

    def register_admin_command(self, command_names):
        print("LEGACY handlers.register_admin_command(): use plugins.register_admin_command")
        plugins.register_admin_command(command_names)

    def get_admin_commands(self, conversation_id):
        print("LEGACY handlers.get_admin_commands(): use command.get_admin_commands")
        return command.get_admin_commands(self.bot, conversation_id)

    """handler core"""

    @asyncio.coroutine
    def handle_chat_message(self, event):
        """Handle conversation event"""
        if logging.root.level == logging.DEBUG:
            event.print_debug()

        if event.text:
            yield from self.run_pluggable_omnibus("allmessages", self.bot, event, command)
            if not event.user.is_self:
                yield from self.run_pluggable_omnibus("message", self.bot, event, command)
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
            self.bot.send_message(event.conv, _('{}: missing parameter(s)').format(event.user.full_name))
            return

        # only admins can run admin commands
        commands_admin_list = command.get_admin_commands(self.bot, event.conv_id)
        if commands_admin_list and line_args[1].lower() in commands_admin_list:
            if not initiator_is_admin:
                self.bot.send_message(event.conv, _('{}: Can\'t do that.').format(event.user.full_name))
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
                                plugin_metadata["module.path"],
                                function.__name__)]

                    try:
                        """accepted handler signatures:
                        coroutine(bot, event, command)
                        coroutine(bot, event)
                        function(bot, event, context)
                        function(bot, event)
                        """
                        _expected = list(inspect.signature(function).parameters)
                        _passed = args[0:len(_expected)]
                        if asyncio.iscoroutinefunction(function):
                            message.append(_("coroutine"))
                            print(" : ".join(message))
                            yield from function(*_passed)
                        else:
                            message.append(_("function"))
                            print(" : ".join(message))
                            function(*_passed)
                    except self.bot.Exceptions.SuppressHandler:
                        # skip this pluggable, continue with next
                        message.append(_("SuppressHandler"))
                        print(" : ".join(message))
                        pass
                    except (self.bot.Exceptions.SuppressEventHandling,
                            self.bot.Exceptions.SuppressAllHandlers):
                        # skip all pluggables, decide whether to handle event at next level
                        raise
                    except:
                        message = " : ".join(message)
                        print(_("EXCEPTION in {}").format(message))
                        logging.exception(message)

            except self.bot.Exceptions.SuppressAllHandlers:
                # skip all other pluggables, but let the event continue
                message.append(_("SuppressAllHandlers"))
                print(" : ".join(message))
                pass
            except:
                raise

class HandlerBridge:
    """shim for xmikosbot handler decorator"""

    def set_bot(self, bot):
        """shim requires a reference to the bot's actual EventHandler to register handlers"""
        self.bot = bot

    def register(self, *args, priority=10, event=None):
        """Decorator for registering event handler"""

        # make compatible with this bot fork
        scaled_priority = priority * 10 # scale for compatibility - xmikos range 1 - 10
        if event is hangups.ChatMessageEvent:
            event_type = "message"
        elif event is hangups.hangups.MembershipChangeEvent:
            event_type = "membership"
        elif event is hangups.hangups.RenameEvent:
            event_type = "rename"
        elif type(event) is str:
            event_type = str # accept all kinds of strings, just like register_handler
        else:
            raise ValueError("unrecognised event {}".format(event))

        def wrapper(func):
            def thunk(bot, event, command):
                # command is an extra parameter supplied in this fork
                return func(bot, event)

            # Automatically wrap handler function in coroutine
            compatible_func = asyncio.coroutine(thunk)
            self.bot._handlers.register_handler(compatible_func, event_type, scaled_priority)
            return compatible_func

        # If there is one (and only one) positional argument and this argument is callable,
        # assume it is the decorator (without any optional keyword arguments)
        if len(args) == 1 and callable(args[0]):
            return wrapper(args[0])
        else:
            return wrapper

handler = HandlerBridge()