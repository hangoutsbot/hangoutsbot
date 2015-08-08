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

    if not cmd or (cmd=="impersonate" and event.user.id_.chat_id in admins_list):

        help_chat_id = event.user.id_.chat_id
        help_conv_id = event.conv_id

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

        commands = command.get_available_commands(bot, help_chat_id, help_conv_id)
        commands_admin = commands["admin"]
        commands_nonadmin = commands["user"]

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
        try:
            command_fn = command.commands[cmd]
            help_lines.append("<b>{}</b>: {}".format(cmd, command_fn.__doc__))
        except KeyError:
            yield from command.unknown_command(bot, event)
            return

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

    bot.send_message(event.conv, message)


@command.register
def ping(bot, event, *args):
    """reply to a ping"""
    bot.send_message(event.conv, 'pong')


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


@command.register(admin=True)
def plugininfo(bot, event, *args):
    """dumps plugin information"""
    text_plugins = []

    for plugin in plugins.tracking.list:
        lines = []
        if len(args) == 0 or args[0] in plugin["metadata"]["module"] or args[0] in plugin["metadata"]["module.path"]:
            lines.append("<b>[ {} ]</b>".format(plugin["metadata"]["module.path"]))

            """admin commands"""
            if len(plugin["commands"]["admin"]) > 0:
                lines.append("<b>admin commands:</b> <pre>{}</pre>".format(", ".join(plugin["commands"]["admin"])))

            """user-only commands"""
            user_only_commands = list(set(plugin["commands"]["user"]) - set(plugin["commands"]["admin"]))
            if len(user_only_commands) > 0:
                lines.append("<b>user commands:</b> <pre>{}</pre>".format(", ".join(user_only_commands)))

            """handlers"""
            if len(plugin["handlers"]) > 0:
                lines.append("<b>handlers:</b>")
                lines.append("<br />".join([ "... <b><pre>{}</pre></b> (<pre>{}</pre>, p={})".format(f[0].__name__, f[1], str(f[2])) for f in plugin["handlers"]]))

            """shared"""
            if len(plugin["shared"]) > 0:
                lines.append("<b>shared:</b> " + ", ".join([ "<pre>{}</pre>".format(f[1].__name__) for f in plugin["shared"]]))

            """tagged"""
            if len(plugin["commands"]["tagged"]) > 0:
                lines.append("<b>tagged via plugin module:</b>")
                for command_name, type_tags in plugin["commands"]["tagged"].items():
                    if 'admin' in type_tags:
                        plugin_tagsets = type_tags['admin']
                    else:
                        plugin_tagsets = type_tags['user']

                    matches = []
                    for tagset in plugin_tagsets:
                        if isinstance(tagset, frozenset):
                            matches.append("[ {} ]".format(', '.join(tagset)))
                        else:
                            matches.append(tagset)

                    lines.append("... <b><pre>{}</pre></b>: <pre>{}</pre>".format(command_name, ', '.join(matches)))

        if len(lines) > 0:
            text_plugins.append("<br />".join(lines))

    if len(text_plugins) > 0:
        message = "<br />".join(text_plugins)
    else:
        message = "nothing to display"

    bot.send_html_to_conversation(event.conv_id, message)


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
    bot.send_message_parsed(event.conv,  "<b>" + message + "</b>")


@command.register_unknown
def unknown_command(bot, event, *args):
    """handle unknown commands"""
    bot.send_message(event.conv,
                     _('{}: unknown command').format(event.user.full_name))
