import logging, pprint

from commands import command


logger = logging.getLogger(__name__)


def _initialise(bot): pass # prevents commands from being automatically added

def _tagshortcuts(event, type, id):
    """given type=conv, type=convuser, id=here expands to event.conv_id"""

    if id == "here":
        if type not in ["conv", "convuser"]:
            raise TypeError("here cannot be used for type {}".format(type))

        id = event.conv_id
        if type == "convuser":
            id += "|*"

    return type, id


@command.register(admin=True)
def tagset(bot, event, *args):
    """set a single tag. usage: tagset <"conv"|"user"|"convuser"> <id> <tag>"""
    if len(args) == 3:
        [type, id, tag] = args
        type, id = _tagshortcuts(event, type, id)
        if bot.tags.add(type, id, tag):
            message = _("tagged <b><pre>{}</pre></b> with <b><pre>{}</pre></b>".format(id, tag))
        else:
            message = _("<b><pre>{}</pre></b> unchanged".format(id))
    else:
        message = _("<b>supply type, id, tag</b>")
    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def tagdel(bot, event, *args):
    """remove single tag. usage: tagdel <"conv"|"user"|"convuser"> <id> <tag>"""
    if len(args) == 3:
        [type, id, tag] = args
        type, id = _tagshortcuts(event, type, id)
        if bot.tags.remove(type, id, tag):
            message = _("removed <b><pre>{}</pre></b> from <b><pre>{}</pre></b>".format(tag, id))
        else:
            message = _("<b><pre>{}</pre></b> unchanged".format(id))
    else:
        message = _("<b>supply type, id, tag</b>")
    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def tagspurge(bot, event, *args):
    """batch remove tags. usage: tagspurge <"user"|"conv"|"convuser"|"tag"|"usertag"|"convtag"> <id|"ALL">"""
    if len(args) == 2:
        [type, id] = args
        type, id = _tagshortcuts(event, type, id)
        entries_removed = bot.tags.purge(type, id)
        message = _("entries removed: <b><pre>{}</pre></b>".format(entries_removed))
    else:
        message = _("<b>supply type, id</b>")
    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def tagscommand(bot, event, *args):
    """display of command tagging information, more complete than plugininfo"""
    if len(args) == 1:
        [command_name] = args

        if command_name not in command.commands:
            message = _("<b><pre>COMMAND: {}</pre></b> does not exist".format(command_name))

        else:
            lines = []

            ALL_TAGS = set()

            plugin_defined = set()
            if command_name in command.command_tagsets:
                plugin_defined = command.command_tagsets[command_name]
                ALL_TAGS = ALL_TAGS | plugin_defined

            config_root = set()
            config_commands_tagged = bot.get_config_option('commands_tagged') or {}
            if command_name in config_commands_tagged and config_commands_tagged[command_name]:
                config_root = set([ frozenset(value if isinstance(value, list) else [value])
                    for value in config_commands_tagged[command_name] ])
                ALL_TAGS = ALL_TAGS | config_root

            config_conv = {}
            if bot.config.exists(["conversations"]):
                for convid in bot.config["conversations"]:
                    if bot.config.exists(["conversations", convid, "commands_tagged"]):
                        conv_tagged = bot.config.get_by_path(["conversations", convid, "commands_tagged"])
                        if command_name in conv_tagged and conv_tagged[command_name]:
                            config_conv[convid] = set([ frozenset(value if isinstance(value, list) else [value])
                                for value in conv_tagged[command_name] ])
                            ALL_TAGS = ALL_TAGS | config_conv[convid]

            dict_tags = {}
            for match in ALL_TAGS:
                text_match = ", ".join(sorted(match))

                if text_match not in dict_tags:
                    dict_tags[text_match] = []

                if match in plugin_defined:
                    dict_tags[text_match].append("plugin")
                if match in config_root:
                    dict_tags[text_match].append("config: root")
                for convid, tagsets in config_conv.items():
                    if match in tagsets:
                        dict_tags[text_match].append("config: {}".format(convid))

            for text_tags in sorted(dict_tags.keys()):
                lines.append("[ {} ]".format(text_tags))
                for source in dict_tags[text_tags]:
                    lines.append("... {}".format(source))

            if len(lines)==0:
                message = _("<b><pre>COMMAND: {}</pre></b> has no tags".format(command_name))
            else:
                lines.insert(0, _("<b><pre>COMMAND: {}</pre></b>, match <b>ANY</b>:".format(command_name)))
                message = "<br />".join(lines)

    else:
        message = _("<b>supply command name</b>")

    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def tagindexdump(bot, event, *args):
    """dump raw contents of tags indices"""
    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(bot.tags.indices)

    chunks = []
    for relationship in bot.tags.indices:
        lines = [_("index: <b><pre>{}</pre></b>").format(relationship)]
        for key, list in bot.tags.indices[relationship].items():
            lines.append(_("key: <pre>{}</pre>").format(key))
            for item in list:
                lines.append("... <pre>{}</pre>".format(item))
        if len(lines) == 0:
            continue
        chunks.append("<br />".join(lines))

    if len(chunks) == 0:
        chunks = [_("<b>no entries to list</b>")]

    yield from bot.coro_send_message(event.conv_id, "<br /><br />".join(chunks))


@command.register(admin=True)
def tagsconv(bot, event, *args):
    """get tag assignments for conversation (default: current conversation). usage: tagsconv [here|<conv id>]"""
    if len(args) == 1:
        conv_id = args[0]
    else:
        conv_id = event.conv_id

    if conv_id == "here":
        conv_id = event.conv_id

    active_conv_tags = bot.tags.convactive(conv_id)
    if active_conv_tags:
        message_taglist = ", ".join([ "<pre>{}</pre>".format(tag) for tag in active_conv_tags ])
    else:
        message_taglist = "<em>no tags returned</em>"

    yield from bot.coro_send_message(event.conv_id,
                                     "<b><pre>{}</pre></b>: {}".format(
                                        conv_id, message_taglist))


@command.register(admin=True)
def tagsuser(bot, event, *args):
    """get tag assignments for a user in an (optional) conversation. usage: tagsuser <user id> [<conv id>]"""
    if len(args) == 1:
        conv_id = "*"
        chat_id = args[0]
    elif len(args) == 2:
        conv_id = args[1]
        chat_id = args[0]
    else:
        yield from bot.coro_send_message(event.conv_id, _("<b>supply chat_id, optional conv_id</b>"))
        return

    if conv_id == "here":
        conv_id = event.conv_id

    active_user_tags = bot.tags.useractive(chat_id, conv_id)
    if active_user_tags:
        message_taglist = ", ".join([ "<pre>{}</pre>".format(tag) for tag in active_user_tags ])
    else:
        message_taglist = "<em>no tags returned</em>"

    yield from bot.coro_send_message(event.conv_id,
                                     "<b><pre>{}</pre></b>@<b><pre>{}</pre></b>: {}".format(
                                        chat_id, conv_id, message_taglist))


@command.register(admin=True)
def tagsuserlist(bot, event, *args):
    """get tag assignments for all users in a conversation, filtered by (optional) taglist. usage: tagsuserlist <conv id> [<tag name> [<tag name>] [...]]"""
    if len(args) == 1:
        conv_id = args[0]
        filter_tags = False
    elif len(args) > 1:
        conv_id = args[0]
        filter_tags = args[1:]
    else:
        yield from bot.coro_send_message(event.conv_id, _("<b>supply conv_id, optional tag list</b>"))
        return

    if conv_id == "here":
        conv_id = event.conv_id

    users_to_tags = bot.tags.userlist(conv_id, filter_tags)

    lines = []
    for chat_id, active_user_tags in users_to_tags.items():
        if not active_user_tags:
            active_user_tags = [_("<em>no tags returned</em>")]
        lines.append("<b><pre>{}</pre></b>: <pre>{}</pre>".format(chat_id, ", ".join(active_user_tags)))

    if len(lines) == 0:
        lines = [_("<b>no users found</b>")]

    yield from bot.coro_send_message(event.conv_id, "<br />".join(lines))
