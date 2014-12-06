import sys, json, random, asyncio

import hangups
from hangups.ui.utils import get_conv_name

from utils import text_to_segments

from pushbullet import PushBullet

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
            print(e)

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


@command.register_unknown
def unknown_command(bot, event, *args):
    """handle unknown commands"""
    bot.send_message(event.conv,
                     '{}: unknown command'.format(event.user.full_name))


@command.register
def help(bot, event, cmd=None, *args):
    """list supported commands"""
    if not cmd:
        segments = [hangups.ChatMessageSegment('supported commands:', is_bold=True),
                    hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                    hangups.ChatMessageSegment(', '.join(sorted(command.commands.keys())))]
    else:
        try:
            command_fn = command.commands[cmd]
            segments = [hangups.ChatMessageSegment('{}:'.format(cmd), is_bold=True),
                        hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
            segments.extend(text_to_segments(command_fn.__doc__))
        except KeyError:
            yield from command.unknown_command(bot, event)
            return

    bot.send_message_segments(event.conv, segments)


@command.register
def ping(bot, event, *args):
    """reply to a ping"""
    bot.send_message(event.conv, 'pong')


@command.register
def echo(bot, event, *args):
    """echo back requested text"""
    bot.send_message(event.conv, '{}'.format(' '.join(args)))


@command.register
def users(bot, event, *args):
    """list all users in current hangout (include g+ and email links)"""
    segments = [hangups.ChatMessageSegment('user list (total {}):'.format(len(event.conv.users)),
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


@command.register
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


@command.register
def hangouts(bot, event, *args):
    """list all active hangouts the bot is participating in
        details: c ... commands, f ... forwarding, a ... autoreplies"""
    segments = [hangups.ChatMessageSegment('list of active hangouts:', is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
    for c in bot.list_conversations():
        s = '{} [c: {:d}, f: {:d}, a: {:d}]'.format(get_conv_name(c, truncate=True),
                                                    bot.get_config_suboption(c.id_, 'commands_enabled'),
                                                    bot.get_config_suboption(c.id_, 'forwarding_enabled'),
                                                    bot.get_config_suboption(c.id_, 'autoreplies_enabled'))
        segments.append(hangups.ChatMessageSegment(s))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))

    bot.send_message_segments(event.conv, segments)


@command.register
def rename(bot, event, *args):
    """rename current hangout"""
    yield from bot._client.setchatname(event.conv_id, ' '.join(args))


@command.register
def leave(bot, event, conversation=None, *args):
    """exits current or other specified hangout"""
    convs = []
    if not conversation:
        convs.append(event.conv)
    else:
        conversation = conversation.strip().lower()
        for c in bot.list_conversations():
            if conversation in get_conv_name(c, truncate=True).lower():
                convs.append(c)

    for c in convs:
        yield from c.send_message([
            hangups.ChatMessageSegment('I\'ll be back!')
        ])
        yield from bot._conv_list.leave_conversation(c.id_)


@command.register
def easteregg(bot, event, easteregg, eggcount=1, period=0.5, *args):
    """starts easter egg combos (parameters : egg [number] [period])
       supported easter eggs: ponies , pitchforks , bikeshed , shydino"""
    for i in range(int(eggcount)):
        yield from bot._client.sendeasteregg(event.conv_id, easteregg)
        if int(eggcount) > 1:
            yield from asyncio.sleep(float(period) + random.uniform(-0.1, 0.1))

@command.register
def reload(bot, event, *args):
    """reloads configuration"""
    bot.config.load()


@command.register
def quit(bot, event, *args):
    """stop running"""
    print('HangupsBot killed by user {} from conversation {}'.format(event.user.full_name,
                                                                     get_conv_name(event.conv, truncate=True)))
    yield from bot._client.disconnect()


@command.register
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
        value = 'parameter does not exist'

    config_path = ' '.join(k for k in ['config'] + config_args)
    segments = [hangups.ChatMessageSegment('{}:'.format(config_path),
                                           is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
    segments.extend(text_to_segments(json.dumps(value, indent=2, sort_keys=True)))
    bot.send_message_segments(event.conv, segments)


@command.register
def mention(bot, event, *args):
    """alert a @mentioned user"""
    username = args[0].strip()
    if len(username) < 2:
        print("@mention must be 2 letters or longer (== '{}')".format(username))
        return
    """verify user is in current conversation, get id"""
    username_lower = username.lower()
    for u in event.conv.users:
        if username_lower == "all" or \
                username_lower in u.full_name.replace(" ", "").lower():

            print('user {} found, chat_id: {}'.format(u.full_name, u.id_.chat_id))

            if u.is_self:
                print("bot cannot be directly mentioned")
                continue

            if u.id_.chat_id == event.user.id_.chat_id and username_lower == "all":
                """prevent initiating user from receiving duplicate @all"""
                print("suppressing @all for initiator {}".format(u.full_name))
                continue

            donotdisturb = bot.config.get('donotdisturb')
            if donotdisturb:
                """user-configured DND"""
                if u.id_.chat_id in donotdisturb:
                    print("global DND for {} ({})".format(u.full_name, u.id_.chat_id))
                    continue

            alert_via_1on1 = True

            """pushbullet integration"""
            pushbullet_integration = bot.get_config_suboption(event.conv.id_, 'pushbullet')
            if pushbullet_integration:
                if u.id_.chat_id in pushbullet_integration.keys():
                    pushbullet_apikey = pushbullet_integration[u.id_.chat_id]
                    if pushbullet_apikey:
                        pb = PushBullet(pushbullet_apikey["api"])
                        success, push = pb.push_note(
                            "{} mentioned you in {}".format(
                                event.user.full_name, 
                                get_conv_name(event.conv, truncate=True)), 
                            event.text)
                        if success:
                            print("{} alerted via pushbullet".format(u.full_name))
                            alert_via_1on1 = False # disable 1on1 alert

            if alert_via_1on1:
                """send alert with 1on1 conversation"""
                conv_1on1 = bot.get_1on1_conversation(u.id_.chat_id)
                if conv_1on1:
                    bot.send_message_parsed(
                        conv_1on1, 
                        "<b>{}</b> @mentioned you in <i>{}</i>:<br />{}".format(
                            event.user.full_name, 
                            get_conv_name(event.conv, truncate=True), 
                            event.text))
                    print("{} alerted via 1on1 with id {}".format(
                            u.full_name, 
                            conv_1on1.id_))
                else:
                    if bot.get_config_suboption(event.conv_id, 'mentionerrors'):
                        bot.send_message_parsed(
                            event.conv, 
                            "Unable to @mention <b>{}</b>. User must talk to me first.".format(
                                u.full_name))
                    print("could not alert user {} via 1on1".format(u.full_name))


@command.register
def pushbulletapi(bot, event, *args):
    """allow users to configure pushbullet integration with api key
        /bot pushbulletapi [<api key>|false, 0, -1]"""

    # XXX: /bot config exposes all configured api keys (security risk!)

    if len(args) == 1:
        value = args[0]
        if value.lower() in ('false', '0', '-1'):
            value = None
            bot.send_message_parsed(
                event.conv, 
                "deactivating pushbullet integration")
        else:
            bot.send_message_parsed(
                event.conv, 
                "setting pushbullet api key")
        bot.config.set_by_path(["pushbullet", event.user.id_.chat_id], { "api": value })
        bot.config.save()
    else:
        bot.send_message_parsed(
            event.conv, 
            "pushbullet configuration not changed")


@command.register
def dnd(bot, event, *args):
    """allow users to toggle DND for ALL conversations (i.e. no @mentions)
        /bot dnd"""

    initiator_chat_id = event.user.id_.chat_id
    dnd_list = bot.config.get_by_path(["donotdisturb"])
    if not initiator_chat_id in dnd_list:
        dnd_list.append(initiator_chat_id)
        bot.send_message_parsed(
            event.conv, 
            "global DND toggled ON for {}".format(event.user.full_name))
    else:
        dnd_list.remove(initiator_chat_id)
        bot.send_message_parsed(
            event.conv, 
            "global DND toggled OFF for {}".format(event.user.full_name))

    bot.config.set_by_path(["donotdisturb"], dnd_list)
    bot.config.save()

@command.register
def whoami(bot, event, *args):
    """whoami"""
    bot.send_message_parsed(event.conv, "<b>{}</b>, chat_id = <i>{}</i>".format(event.user.full_name, event.user.id_.chat_id))
