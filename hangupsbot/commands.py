import sys, json, asyncio, logging, os

import hangups
from hangups.ui.utils import get_conv_name

from utils import text_to_segments


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
            message = _("CommandDispatcher.run: {}").format(func.__name__)
            print(_("EXCEPTION in {}").format(message))
            logging.exception(message)


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
    """list supported commands, /bot help <command> will show additional details"""
    help_lines = []
    link_to_guide = bot.get_config_suboption(event.conv_id, 'link_to_guide')
    if not cmd:
        admins_list = bot.get_config_suboption(event.conv_id, 'admins')

        commands_all = command.commands.keys()
        commands_admin = bot._handlers.get_admin_commands(event.conv_id)
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
        bot.send_message_parsed(event.conv, _('<i>{}, you <b>opted-out</b> from bot private messages</i>'.format(event.user.full_name)))
    else:
        bot.send_message_parsed(event.conv, _('<i>{}, you <b>opted-in</b> for bot private messages</i>'.format(event.user.full_name)))


@command.register_unknown
def unknown_command(bot, event, *args):
    """handle unknown commands"""
    bot.send_message(event.conv,
                     _('{}: unknown command').format(event.user.full_name))
