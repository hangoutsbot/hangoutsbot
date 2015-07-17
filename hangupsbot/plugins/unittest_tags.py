import hangups

import plugins

def _initialise(bot):
    plugins.register_admin_command(["tagset", "tagdel", "tagindexdump", "tagcheck"])


def tagset(bot, event, *args):
    if len(args) == 3:
        [type, id, tag] = args
        if bot.tags.add(type, id, tag):
            message = _("<b>tagged `{}` with `{}`</b>".format(id, tag))
        else:
            message = _("<b>`{}` not tagged with `{}`</b>".format(id, tag))
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

def tagcheck(bot, event, *args):
    if len(args) == 3:
        [type, id, tag] = args

        results = bot.tags.check(type, id, tag)

        if results:
            message = _("<b>`{}` tagged with `{}`</b>").format(id, tag)
        else:
            message = _("<b>`{}` not tagged with `{}`</b>").format(id, tag)
    else:
        message = _("<b>supply type, id, tag</b>")

    bot.send_message_parsed(event.conv_id, message)

def tagindexdump(bot, event, *args):
    groupings = []
    for type in ["user", "conv"]:
        for tag, idlist in bot.tags.indices[type].items():
            entries = []
            for id in idlist:
                if type == "conv":
                    label = bot.conversations.get_name(id)
                else:
                    # XXX: needs a more reliable way to get user info
                    try:
                        user_id = hangups.user.UserID(chat_id=id, gaia_id=id)
                        _u = bot._user_list._user_dict[user_id]
                        label = _u.full_name
                    except KeyError:
                        label = _("unknown user")
                entries.append("`{}` <b>`{}`</b>".format(id, label))
            if len(entries) > 0:
                entries.insert(0, _("<b>type: {}, tag: {}</b>").format(type, tag))
                groupings.append("<br />".join(entries))

    if len(groupings) == 0:
        groupings.append(_("<b>no entries have tags</b>"))

    bot.send_message_parsed(event.conv_id, '<br />'.join(groupings))
