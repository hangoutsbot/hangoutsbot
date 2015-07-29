import pprint

import hangups

import plugins

def _initialise(bot):
    plugins.register_admin_command(["tagset", "tagdel", "tagindexdump", "tagspurge", "tagsuser", "tagsuserlist"])


def tagset(bot, event, *args):
    if len(args) == 3:
        [type, id, tag] = args
        if bot.tags.add(type, id, tag):
            message = _("<b>tagged `{}` with `{}`</b>".format(id, tag))
        else:
            message = _("<b>`{}` unchanged</b>".format(id))
    else:
        message = _("<b>supply type, id, tag</b>")
    bot.send_message_parsed(event.conv_id, message)


def tagdel(bot, event, *args):
    if len(args) == 3:
        [type, id, tag] = args
        if bot.tags.remove(type, id, tag):
            message = _("<b>removed `{}` from `{}`</b>".format(tag, id))
        else:
            message = _("<b>`{}` unchanged</b>".format(id))
    else:
        message = _("<b>supply type, id, tag</b>")
    bot.send_message_parsed(event.conv_id, message)


def tagspurge(bot, event, *args):
    if len(args) == 2:
        [type, id] = args
        entries_removed = bot.tags.purge(type, id)
        message = _("<b>entries removed: {}</b>".format(entries_removed))
    else:
        message = _("<b>supply type, id</b>")
    bot.send_message_parsed(event.conv_id, message)


def tagindexdump(bot, event, *args):
    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(bot.tags.indices)

    chunks = []
    for relationship in bot.tags.indices:
        lines = [_("<b>index: {}</b>").format(relationship)]
        for key, list in bot.tags.indices[relationship].items():
            lines.append(_("key: {}").format(key))
            for item in list:
                lines.append("... {}".format(item))
        if len(lines) == 0:
            continue
        chunks.append("<br />".join(lines))

    if len(chunks) == 0:
        chunks = [_("<b>no entries to list</b>")]

    bot.send_message_parsed(event.conv_id, "<br /><br />".join(chunks))


def tagsuser(bot, event, *args):
    if len(args) == 1:
        conv_id = "*"
        chat_id = args[0]
    elif len(args) == 2:
        conv_id = args[1]
        chat_id = args[0]
    else:
        bot.send_message_parsed(event.conv_id, _("<b>supply chat_id, optional conv_id</b>"))
        return

    active_user_tags = bot.tags.useractive(chat_id, conv_id)
    if not active_user_tags:
        active_user_tags = [_("<em>no tags returned</em>")]

    bot.send_message_parsed(event.conv_id, "<b><pre>{}@{}</pre></b>: {}".format(
        chat_id, conv_id, ", ".join(active_user_tags)))


def tagsuserlist(bot, event, *args):
    if len(args) == 1:
        conv_id = args[0]
        filter_tags = False
    elif len(args) > 1:
        conv_id = args[0]
        filter_tags = args[1:]
    else:
        bot.send_message_parsed(event.conv_id, _("<b>supply conv_id, optional tag list</b>"))
        return

    users_to_tags = bot.tags.userlist(conv_id, filter_tags)

    lines = []
    for chat_id, active_user_tags in users_to_tags.items():
        if not active_user_tags:
            active_user_tags = [_("<em>no tags returned</em>")]
        lines.append("<b><pre>{}</pre></b>: {}".format(chat_id, ", ".join(active_user_tags)))

    if len(lines) == 0:
        lines = [_("<b>no users found</b>")]

    bot.send_message_parsed(event.conv_id, "<br />".join(lines))
