import json

import hangups
from hangups.ui.utils import get_conv_name

import plugins

from utils import text_to_segments, simple_parse_to_segments


_internal = {} # non-persistent internal state independent of config.json/memory.json

_internal["broadcast"] = { "message": "", "conversations": [] } # /bot broadcast

def _initialise(Handlers, bot=None):
    admin_commands = ["broadcast", "users", "user", "hangouts", "hangout", "rename", "leave", "reload", "quit", "config", "whereami"]
    user_commands = ["echo", "echoparsed", "whoami"]
    try:
        plugins.register_admin_command(admin_commands)
        plugins.register_user_command(user_commands)
    except Exception as e:
        if "register_admin_command" in dir(Handlers) and "register_user_command" in dir(Handlers):
            print(_("DEFAULT: LEGACY FRAMEWORK MODE"))
            Handlers.register_admin_command(admin_commands)
            Handlers.register_user_command(user_commands)
        else:
            print(_("DEFAULT: OBSOLETE FRAMEWORK MODE"))
            return admin_commands + user_commands
    return []


def echo(bot, event, *args):
    """echo back requested text"""

    # Check if the first argument is a known conv_id match
    if args[0] in list(bot.memory.get_by_path(["conv_data"]).keys()):
        text = ' '.join(args[1:])
        conv_id = args[0]

    else:
        text = ' '.join(args)
        conv_id = event.conv_id

    if text.lower().strip().startswith(tuple([cmd.lower() for cmd in bot._handlers.bot_command])):
        text = _("NOPE! Some things aren't worth repeating.")
        conv_id = event.conv_id

    bot.send_message(conv_id, text)


def echoparsed(bot, event, *args):
    """echo back requested text"""

    # Check if the first argument is a known conv_id match
    if args[0] in list(bot.memory.get_by_path(["conv_data"]).keys()):
        formatted_text = ' '.join(args[1:])
        conv_id = args[0]

    else:
        formatted_text = ' '.join(args)
        conv_id = event.conv_id

    test_segments = simple_parse_to_segments(formatted_text)
    if test_segments:
        if test_segments[0].text.strip().startswith(tuple([cmd.lower() for cmd in bot._handlers.bot_command])):
            formatted_text = _("NOPE! Some things aren't worth repeating.")
            conv_id = event.conv_id

    bot.send_message_parsed(conv_id, formatted_text)


def broadcast(bot, event, *args):
    """broadcast a message to chats, use with care"""
    if args:
        subcmd = args[0]
        parameters = args[1:]
        if subcmd == "info":
            """display broadcast data such as message and target rooms"""
            conv_info = ["<b>{}</b> ... {}".format(get_conv_name(_), _.id_) for _ in _internal["broadcast"]["conversations"]]
            if not _internal["broadcast"]["message"]:
                bot.send_message_parsed(event.conv, _("broadcast: no message set"))
                return
            if not conv_info:
                bot.send_message_parsed(event.conv, _("broadcast: no conversations available"))
                return
            bot.send_message_parsed(event.conv, _(
                                            "<b>message:</b><br />"
                                            "{}<br />"
                                            "<b>to:</b><br />"
                                            "{}".format(_internal["broadcast"]["message"],
                                                "<br />".join(conv_info))))
        elif subcmd == "message":
            """set broadcast message"""
            message = ' '.join(parameters)
            if message:
                if message.lower().strip().startswith(tuple([_.lower() for _ in bot._handlers.bot_command])):
                    bot.send_message_parsed(event.conv, _("broadcast: message not allowed"))
                    return
                _internal["broadcast"]["message"] = message
            else:
                bot.send_message_parsed(event.conv, _("broadcast: message must be supplied after subcommand"))
        elif subcmd == "add":
            """add conversations to a broadcast"""
            if parameters[0] == "groups":
                """add all groups (chats with users > 2)"""
                for conv in bot.list_conversations():
                    if len(conv.users) > 2:
                        _internal["broadcast"]["conversations"].append(conv)
            elif parameters[0] == "ALL":
                """add EVERYTHING - try not to use this, will message 1-to-1s as well"""
                for conv in bot.list_conversations():
                    _internal["broadcast"]["conversations"].append(conv)
            else:
                """add by wild card search of title or id"""
                search = " ".join(parameters)
                for conv in bot.list_conversations():
                    if search.lower() in get_conv_name(conv).lower() or search in conv.id_:
                        _internal["broadcast"]["conversations"].append(conv)
            _internal["broadcast"]["conversations"] = list(set(_internal["broadcast"]["conversations"]))
            bot.send_message_parsed(event.conv, _("broadcast: {} conversation(s)".format(len(_internal["broadcast"]["conversations"]))))
        elif subcmd == "remove":
            if parameters[0].lower() == "all":
                """remove all conversations from broadcast"""
                _internal["broadcast"]["conversations"] = []
            else:
                """remove by wild card search of title or id"""
                search = " ".join(parameters)
                removed = []
                for conv in _internal["broadcast"]["conversations"]:
                    if search.lower() in get_conv_name(conv).lower() or search in conv.id_:
                        _internal["broadcast"]["conversations"].remove(conv)
                        removed.append("<b>{}</b> ({})".format(get_conv_name(conv), conv.id_))
                if removed:
                    bot.send_message_parsed(event.conv, _("broadcast: removed {}".format(", ".join(removed))))
        elif subcmd == "NOW":
            """send the broadcast - no turning back!"""
            context = { "explicit_relay": True } # prevent echos across syncrooms
            for conv in _internal["broadcast"]["conversations"]:
                bot.send_message_parsed(conv, _internal["broadcast"]["message"], context=context)
            bot.send_message_parsed(event.conv, _("broadcast: message sent to {} chats".format(len(_internal["broadcast"]["conversations"]))))
        else:
            bot.send_message_parsed(event.conv, _("broadcast: /bot broadcast [info|message|add|remove|NOW] ..."))
    else:
        bot.send_message_parsed(event.conv, _("broadcast: /bot broadcast [info|message|add|remove|NOW]"))


def users(bot, event, *args):
    """list all users in current hangout (include g+ and email links)"""
    segments = [hangups.ChatMessageSegment('User List (total {}):'.format(len(event.conv.users)),
                                           is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
    for u in sorted(event.conv.users, key=lambda x: x.full_name.split()[-1]):
        link = 'https://plus.google.com/u/0/{}/about'.format(u.id_.chat_id)
        segments.append(hangups.ChatMessageSegment(u.full_name, hangups.SegmentType.LINK,
                                                   link_target=link))
        if u.emails:
            segments.append(hangups.ChatMessageSegment(' ('))
            segments.append(hangups.ChatMessageSegment(u.emails[0], hangups.SegmentType.LINK,
                                                       link_target='mailto:{}'.format(u.emails[0])))
            segments.append(hangups.ChatMessageSegment(')'))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    bot.send_message_segments(event.conv, segments)


def user(bot, event, username, *args):
    """find people by name"""
    username_lower = username.strip().lower()
    segments = [hangups.ChatMessageSegment(_('results for user named "{}":').format(username),
                                           is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
    for u in sorted(bot._user_list._user_dict.values(), key=lambda x: x.full_name.split()[-1]):
        if not username_lower in u.full_name.lower():
            continue

        link = 'https://plus.google.com/u/0/{}/about'.format(u.id_.chat_id)
        segments.append(hangups.ChatMessageSegment(u.full_name, hangups.SegmentType.LINK,
                                                   link_target=link))
        if u.emails:
            segments.append(hangups.ChatMessageSegment(' ('))
            segments.append(hangups.ChatMessageSegment(u.emails[0], hangups.SegmentType.LINK,
                                                       link_target='mailto:{}'.format(u.emails[0])))
            segments.append(hangups.ChatMessageSegment(')'))
        segments.append(hangups.ChatMessageSegment(' ... {}'.format(u.id_.chat_id)))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    bot.send_message_segments(event.conv, segments)


def hangouts(bot, event, *args):
    """list all active hangouts. Use '/bot hangouts id' to return the conv_id too
    key: c = commands enabled
    """

    line = _("<b>list of active hangouts:</b><br />")

    for c in bot.list_conversations():
        line += "<b>{}</b>: <i>{}</i>".format(get_conv_name(c, truncate=True), c.id_)

        suboptions = []

        _value = bot.get_config_suboption(c.id_, 'commands_enabled')
        if _value:
            suboptions.append("c")
        if len(suboptions) > 0:
            line += ' [ ' + ', '.join(suboptions) + ' ]'

        line += "<br />"

    bot.send_message_parsed(event.conv, line)


def hangout(bot, event, *args):
    """list all hangouts matching search text"""
    text_search = ' '.join(args)
    if not text_search:
        return
    text_message = _('<b>results for hangouts named "{}"</b><br />').format(text_search)
    for conv in bot.list_conversations():
        conv_name = get_conv_name(conv)
        if text_search.lower() in conv_name.lower():
            text_message = text_message + "<i>" + conv_name + "</i>"
            text_message = text_message + " ... " + conv.id_
            text_message = text_message + "<br />"
    bot.send_message_parsed(event.conv.id_, text_message)


def rename(bot, event, *args):
    """rename Hangout"""
    yield from bot._client.setchatname(event.conv_id, ' '.join(args))


def leave(bot, event, conversation_id=None, *args):
    """exits current or other specified hangout"""

    leave_quietly = False
    convs = []

    if not conversation_id:
        convs.append(event.conv.id_)
    elif conversation_id=="quietly":
        convs.append(event.conv.id_)
        leave_quietly = True
    else:
        convs.append(conversation_id)

    for c_id in convs:
        if not leave_quietly:
            bot.send_message_parsed(c_id, _('I\'ll be back!'))
        yield from bot._conv_list.leave_conversation(c_id)


def reload(bot, event, *args):
    """reload config and memory, useful if manually edited on running bot"""
    bot.config.load()
    bot.memory.load()


def quit(bot, event, *args):
    """stop running"""
    print(_('HangupsBot killed by user {} from conversation {}').format(event.user.full_name,
                                                                     get_conv_name(event.conv, truncate=True)))
    yield from bot._client.disconnect()


def config(bot, event, cmd=None, *args):
    """displays or modifies the configuration
        Parameters: /bot config get [key] [subkey] [...]
                    /bot config set [key] [subkey] [...] [value]
                    /bot config append [key] [subkey] [...] [value]
                    /bot config remove [key] [subkey] [...] [value]"""

    # consume arguments and differentiate beginning of a json array or object
    tokens = list(args)
    parameters = []
    value = []
    state = "key"
    for token in tokens:
        if token.startswith(("{", "[")):
            # apparent start of json array/object, consume into a single list item
            state = "json"
        if state == "key":
            parameters.append(token)
        elif state == "json":
            value.append(token)
        else:
            raise ValueError("unknown state")
    if value:
        parameters.append(" ".join(value))
    print("config {}".format(parameters))

    if cmd == 'get' or cmd is None:
        config_args = list(parameters)
        value = bot.config.get_by_path(config_args) if config_args else dict(bot.config)
    elif cmd == 'set':
        config_args = list(parameters[:-1])
        if len(parameters) >= 2:
            bot.config.set_by_path(config_args, json.loads(parameters[-1]))
            bot.config.save()
            value = bot.config.get_by_path(config_args)
        else:
            yield from command.unknown_command(bot, event)
            return
    elif cmd == 'append':
        config_args = list(parameters[:-1])
        if len(parameters) >= 2:
            value = bot.config.get_by_path(config_args)
            if isinstance(value, list):
                value.append(json.loads(parameters[-1]))
                bot.config.set_by_path(config_args, value)
                bot.config.save()
            else:
                value = _('append failed on non-list')
        else:
            yield from command.unknown_command(bot, event)
            return
    elif cmd == 'remove':
        config_args = list(parameters[:-1])
        if len(parameters) >= 2:
            value = bot.config.get_by_path(config_args)
            if isinstance(value, list):
                value.remove(json.loads(parameters[-1]))
                bot.config.set_by_path(config_args, value)
                bot.config.save()
            else:
                value = _('remove failed on non-list')
        else:
            yield from command.unknown_command(bot, event)
            return
    else:
        yield from command.unknown_command(bot, event)
        return

    if value is None:
        value = _('Parameter does not exist!')

    config_path = ' '.join(k for k in ['config'] + config_args)
    segments = [hangups.ChatMessageSegment('{}:'.format(config_path),
                                           is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
    segments.extend(text_to_segments(json.dumps(value, indent=2, sort_keys=True)))
    bot.send_message_segments(event.conv, segments)


def whoami(bot, event, *args):
    """get your user id"""

    if bot.memory.exists(['user_data', event.user_id.chat_id, "nickname"]):
        try:
            fullname = '{0} ({1})'.format(event.user.full_name.split(' ', 1)[0]
                , bot.get_memory_suboption(event.user_id.chat_id, 'nickname'))
        except TypeError:
            fullname = event.user.full_name
    else:
        fullname = event.user.full_name

    bot.send_message_parsed(event.conv, _("<b>{}</b>, chat_id = <i>{}</i>").format(fullname, event.user.id_.chat_id))


def whereami(bot, event, *args):
    """get current conversation id"""

    bot.send_message_parsed(
      event.conv,
      _("You are at <b>{}</b>, conv_id = <i>{}</i>").format(
        get_conv_name(event.conv, truncate=True),
        event.conv.id_))
