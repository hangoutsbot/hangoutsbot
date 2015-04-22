import sys, json, asyncio, logging, os

import hangups
from hangups.ui.utils import get_conv_name

from version import __version__
from utils import text_to_segments

import plugins


class CommandDispatcher(object):
    """Register commands and run them"""
    def __init__(self):
        self.commands = {}
        self.admin_commands = []
        self.unknown_command = None
        self.tracking = None

    def set_tracking(self, tracking):
        self.tracking = tracking

    def get_admin_commands(self, bot, conv_id):
        """Get list of admin-only commands (set by plugins or in config.json)"""
        commands_admin = bot.get_config_suboption(conv_id, 'commands_admin') or []
        return list(set(commands_admin + self.admin_commands))

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

        args = list(args[1:])

        try:
            yield from func(bot, event, *args, **kwds)
        except Exception as e:
            message = _("CommandDispatcher.run: {}").format(func.__name__)
            print(_("EXCEPTION in {}").format(message))
            logging.exception(message)

    def register(self, *args, admin=False):
        """Decorator for registering command"""
        def wrapper(func):
            # Automatically wrap command function in coroutine
            func = asyncio.coroutine(func)
            self.commands[func.__name__] = func
            if self.tracking:
                plugins.tracking.register_command("user", [func.__name__])
            if admin:
                self.admin_commands.append(func.__name__)
                if self.tracking:
                    plugins.tracking.register_command("admin", [func.__name__])
            return func

        # If there is one (and only one) positional argument and this argument is callable,
        # assume it is the decorator (without any optional keyword arguments)
        if len(args) == 1 and callable(args[0]):
            return wrapper(args[0])
        else:
            return wrapper

    def register_unknown(self, func):
        """Decorator for registering unknown command"""
        self.unknown_command = asyncio.coroutine(func)
        return func


# CommandDispatcher singleton
command = CommandDispatcher()

@command.register
def help(bot, event, cmd=None, *args):
    """list supported commands, /bot help <command> will show additional details"""
    help_lines = []
    link_to_guide = bot.get_config_suboption(event.conv_id, 'link_to_guide')
    if not cmd:
        admins_list = bot.get_config_suboption(event.conv_id, 'admins')

        commands_all = command.commands.keys()
        commands_admin = command.get_admin_commands(bot, event.conv_id)
        commands_nonadmin = list(set(commands_all) - set(commands_admin))

        help_lines.append(_('<b>User commands:</b>'))
        help_lines.append(', '.join(sorted(commands_nonadmin)))

        if link_to_guide:
            help_lines.append('')
            help_lines.append(_('<i>For more information, please see: {}</i>').format(link_to_guide))

        if event.user_id.chat_id in admins_list:
            help_lines.append('')
            help_lines.append(_('<b>Admin commands:</b>'))
            help_lines.append(', '.join(sorted(commands_admin)))
    else:
        try:
            command_fn = command.commands[cmd]
            help_lines.append("<b>{}</b>: {}".format(cmd, command_fn.__doc__))
        except KeyError:
            yield from command.unknown_command(bot, event)
            return

    # help can get pretty long, so we send a short message publicly, and the actual help privately
    conv_1on1_initiator = bot.get_1on1_conversation(event.user.id_.chat_id)
    if conv_1on1_initiator:
        bot.send_message_parsed(conv_1on1_initiator, "<br />".join(help_lines))
        if conv_1on1_initiator.id_ != event.conv_id:
            bot.send_message_parsed(event.conv, _("<i>{}, I've sent you some help ;)</i>").format(event.user.full_name))
    else:
        bot.send_message_parsed(event.conv, _("<i>{}, before I can help you, you need to private message me and say hi.</i>").format(event.user.full_name))


@command.register
def ping(bot, event, *args):
    """reply to a ping"""
    bot.send_message(event.conv, _('pong'))


@command.register
def optout(bot, event, *args):
    """toggle opt-out of bot PM"""
    optout = False
    chat_id = event.user.id_.chat_id
    bot.initialise_memory(chat_id, "user_data")
    if bot.memory.exists(["user_data", chat_id, "optout"]):
        optout = bot.memory.get_by_path(["user_data", chat_id, "optout"])
    optout = not optout

    bot.memory.set_by_path(["user_data", chat_id, "optout"], optout)
    bot.memory.save()

    if optout:
        bot.send_message_parsed(event.conv, _('<i>{}, you <b>opted-out</b> from bot private messages</i>').format(event.user.full_name))
    else:
        bot.send_message_parsed(event.conv, _('<i>{}, you <b>opted-in</b> for bot private messages</i>').format(event.user.full_name))


@command.register
def version(bot, event, *args):
    """get the version of the bot"""
    bot.send_message_parsed(event.conv, _("Bot Version: <b>{}</b>").format(__version__))


@command.register_unknown
def unknown_command(bot, event, *args):
    """handle unknown commands"""
    bot.send_message(event.conv,
                     _('{}: unknown command').format(event.user.full_name))
