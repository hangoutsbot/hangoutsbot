import logging, sys, resource

import plugins

from version import __version__
from commands import command


logger = logging.getLogger(__name__)


def _initialise(bot): pass # prevents commands from being automatically added


@command.register
def help(bot, event, cmd=None, *args):
    """list supported commands, /bot help <command> will show additional details"""
    help_lines = []
    link_to_guide = bot.get_config_suboption(event.conv_id, 'link_to_guide')
    admins_list = bot.get_config_suboption(event.conv_id, 'admins')

    help_chat_id = event.user.id_.chat_id
    help_conv_id = event.conv_id
    commands = command.get_available_commands(bot, help_chat_id, help_conv_id)
    commands_admin = commands["admin"]
    commands_nonadmin = commands["user"]

    if not cmd or (cmd=="impersonate" and event.user.id_.chat_id in admins_list):

        if cmd == "impersonate":
            if len(args) == 1:
                [help_chat_id] = args
            elif len(args) == 2:
                [help_chat_id, help_conv_id] = args
            else:
                raise ValueError("impersonation: supply chat id and optional conversation id")

            help_lines.append(_('<b>Impersonation:</b><br />'
                                '<b><pre>{}</pre></b><br />'
                                '<b><pre>{}</pre></b><br />').format( help_chat_id,
                                                                      help_conv_id ))

        if len(commands_nonadmin) > 0:
            help_lines.append(_('<b>User commands:</b>'))
            help_lines.append(', '.join(sorted(commands_nonadmin)))

        if link_to_guide:
            help_lines.append('')
            help_lines.append(_('<i>For more information, please see: {}</i>').format(link_to_guide))

        if len(commands_admin) > 0:
            help_lines.append('')
            help_lines.append(_('<b>Admin commands:</b>'))
            help_lines.append(', '.join(sorted(commands_admin)))
    else:
        if cmd in command.commands and (cmd in commands_admin or cmd in commands_nonadmin):
            command_fn = command.commands[cmd]
        elif cmd.lower() in command.commands and (cmd in commands_admin or cmd in commands_nonadmin):
            command_fn = command.commands[cmd.lower()]
        else:
            yield from command.unknown_command(bot, event)
            return

        help_lines.append("<b>{}</b>: {}".format(command_fn.__name__, command_fn.__doc__))

    yield from bot.coro_send_to_user_and_conversation(
        event.user.id_.chat_id,
        event.conv_id,
        "<br />".join(help_lines), # via private message
        _("<i>{}, I've sent you some help ;)</i>") # public message
            .format(event.user.full_name))


@command.register(admin=True)
def locale(bot, event, *args):
    """set bot localisation"""
    if len(args) > 0:
        if bot.set_locale(args[0], reuse = (False if "reload" in args else True)):
            message = _("locale set to: {}".format(args[0]))
        else:
            message = _("locale unchanged")
    else:
        message = _("language code required")

    yield from bot.coro_send_message(event.conv, message)


@command.register
def ping(bot, event, *args):
    """reply to a ping"""
    yield from bot.coro_send_message(event.conv, 'pong')

    return { "api.response": "pong" }


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
        message = _('<i>{}, you <b>opted-out</b> from bot private messages</i>').format(event.user.full_name)
    else:
        message = _('<i>{}, you <b>opted-in</b> for bot private messages</i>').format(event.user.full_name)

    yield from bot.coro_send_message(event.conv, message)


@command.register
def version(bot, event, *args):
    """get the version of the bot"""
    yield from bot.coro_send_message(event.conv, _("Bot Version: <b>{}</b>").format(__version__))


@command.register(admin=True)
def resourcememory(bot, event, *args):
    """print basic information about memory usage with resource library"""
    # http://fa.bianp.net/blog/2013/different-ways-to-get-memory-consumption-or-lessons-learned-from-memory_profiler/
    rusage_denom = 1024.
    if sys.platform == 'darwin':
        # ... it seems that in OSX the output is different units ...
        rusage_denom = rusage_denom * rusage_denom
    mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / rusage_denom

    message = "memory (resource): {} MB".format(mem)
    logger.info(message)
    yield from bot.coro_send_message(event.conv,  "<b>" + message + "</b>")


@command.register_unknown
def unknown_command(bot, event, *args):
    """handle unknown commands"""
    config_silent = bot.get_config_suboption(event.conv.id_, 'silentmode')
    tagged_silent = "silent" in bot.tags.useractive(event.user_id.chat_id, event.conv.id_)
    if not (config_silent or tagged_silent):

        yield from bot.coro_send_message( event.conv,
                                      _('{}: Unknown Command').format(event.user.full_name) )


@command.register_blocked
def blocked_command(bot, event, *args):
    """handle blocked commands"""
    config_silent = bot.get_config_suboption(event.conv.id_, 'silentmode')
    tagged_silent = "silent" in bot.tags.useractive(event.user_id.chat_id, event.conv.id_)
    if not (config_silent or tagged_silent):
        
        yield from bot.coro_send_message(event.conv, _('{}: Can\'t do that.').format(
        event.user.full_name))
