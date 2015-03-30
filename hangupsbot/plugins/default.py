import json

import hangups
from hangups.ui.utils import get_conv_name

from utils import text_to_segments

def _initialise(Handlers, bot=None):
    if "register_admin_command" in dir(Handlers) and "register_user_command" in dir(Handlers):
        Handlers.register_admin_command(["users", "user", "hangouts", "hangout", "rename", "leave", "reload", "quit", "config", "whereami"])
        Handlers.register_user_command(["whoami", "echo"])
        return []
    else:
        print("DEFAULT: LEGACY FRAMEWORK MODE")
        return ["users", "user", "hangouts", "rename", "leave", "reload", "quit", "config", "whoami", "whereami", "echo", "hangout"]


def echo(bot, event, *args):
    """echo back requested text"""
    text = ' '.join(args)
    if text.lower().strip().startswith("/bot "):
        text = "NOPE! Some things aren't worth repeating."
    bot.send_message(event.conv, text)


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
    segments = [hangups.ChatMessageSegment('results for user named "{}":'.format(username),
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

    line = "<b>list of active hangouts:</b><br />"

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
    text_message = '<b>results for hangouts named "{}"</b><br />'.format(text_search)
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
            bot.send_message_parsed(c_id, 'I\'ll be back!')
        yield from bot._conv_list.leave_conversation(c_id)


def reload(bot, event, *args):
    """reload config and memory, useful if manually edited on running bot"""
    bot.config.load()
    bot.memory.load()


def quit(bot, event, *args):
    """stop running"""
    print('HangupsBot killed by user {} from conversation {}'.format(event.user.full_name,
                                                                     get_conv_name(event.conv, truncate=True)))
    yield from bot._client.disconnect()


def config(bot, event, cmd=None, *args):
    """displays or modifies the configuration
        Parameters: /bot config get [key] [subkey] [...]
                    /bot config set [key] [subkey] [...] [value]
                    /bot config append [key] [subkey] [...] [value]
                    /bot config remove [key] [subkey] [...] [value]"""

    if cmd == 'get' or cmd is None:
        config_args = list(args)
        value = bot.config.get_by_path(config_args) if config_args else dict(bot.config)
    elif cmd == 'set':
        config_args = list(args[:-1])
        if len(args) >= 2:
            bot.config.set_by_path(config_args, json.loads(args[-1]))
            bot.config.save()
            value = bot.config.get_by_path(config_args)
        else:
            yield from command.unknown_command(bot, event)
            return
    elif cmd == 'append':
        config_args = list(args[:-1])
        if len(args) >= 2:
            value = bot.config.get_by_path(config_args)
            if isinstance(value, list):
                value.append(json.loads(args[-1]))
                bot.config.set_by_path(config_args, value)
                bot.config.save()
            else:
                value = 'append failed on non-list'
        else:
            yield from command.unknown_command(bot, event)
            return
    elif cmd == 'remove':
        config_args = list(args[:-1])
        if len(args) >= 2:
            value = bot.config.get_by_path(config_args)
            if isinstance(value, list):
                value.remove(json.loads(args[-1]))
                bot.config.set_by_path(config_args, value)
                bot.config.save()
            else:
                value = 'remove failed on non-list'
        else:
            yield from command.unknown_command(bot, event)
            return
    else:
        yield from command.unknown_command(bot, event)
        return

    if value is None:
        value = 'Parameter does not exist!'

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

    bot.send_message_parsed(event.conv, "<b>{}</b>, chat_id = <i>{}</i>".format(fullname, event.user.id_.chat_id))


def whereami(bot, event, *args):
    """get current conversation id"""

    bot.send_message_parsed(
      event.conv,
      "You are at <b>{}</b>, conv_id = <i>{}</i>".format(
        get_conv_name(event.conv, truncate=True),
        event.conv.id_))
