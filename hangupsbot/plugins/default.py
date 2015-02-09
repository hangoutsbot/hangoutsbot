import json

import hangups
from hangups.ui.utils import get_conv_name

from utils import text_to_segments

def _initialise(command):
    return ["users", "user", "hangouts", "rename", "leave", "reload", "quit", "config", "whoami", "whereami", "echo"]


def echo(bot, event, *args):
    """echo back requested text"""
    bot.send_message(event.conv, '{}'.format(' '.join(args)))


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
    """list all active hangouts the bot is participating in
        details: c ... commands, f ... forwarding, a ... autoreplies"""

    line = "<b>list of active hangouts:</b><br />"

    for c in bot.list_conversations():
        line = line + "{}".format(get_conv_name(c, truncate=True))

        suboptions = []

        _value = bot.get_config_suboption(c.id_, 'commands_enabled')
        if _value:
            suboptions.append("c")
        _value = bot.get_config_suboption(c.id_, 'forwarding_enabled')
        if _value:
            suboptions.append("f")
        _value = bot.get_config_suboption(c.id_, 'autoreplies_enabled')
        if _value:
            suboptions.append("a")

        if len(suboptions) > 0:
            line = line + ' [ ' + ', '.join(suboptions) + ' ]'

        line = line + "<br />"

    bot.send_message_parsed(event.conv, line)


def rename(bot, event, *args):
    """Rename Hangout"""
    yield from bot._client.setchatname(event.conv_id, ' '.join(args))


def leave(bot, event, conversation=None, *args):
    """exits current or other specified hangout"""

    leave_quietly = False
    convs = []

    if not conversation:
        convs.append(event.conv)
    elif conversation=="quietly":
        convs.append(event.conv)
        leave_quietly = True
    else:
        conversation = conversation.strip().lower()
        for c in bot.list_conversations():
            if conversation in get_conv_name(c, truncate=True).lower():
                convs.append(c)

    for c in convs:
        if not leave_quietly:
            yield from c.send_message([
                hangups.ChatMessageSegment('I\'ll be back!')
            ])
        yield from bot._conv_list.leave_conversation(c.id_)


def reload(bot, event, *args):
    """Reload config"""
    bot.config.load()


def quit(bot, event, *args):
    """stop running"""
    print('HangupsBot killed by user {} from conversation {}'.format(event.user.full_name,
                                                                     get_conv_name(event.conv, truncate=True)))
    yield from bot._client.disconnect()


def config(bot, event, cmd=None, *args):
    """Displays or modifies the configuration
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
    """whoami: get user id"""

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
    """whereami: get conversation id"""
    bot.send_message_parsed(
      event.conv,
      "You are at <b>{}</b>, conv_id = <i>{}</i>".format(
        get_conv_name(event.conv, truncate=True),
        event.conv.id_))