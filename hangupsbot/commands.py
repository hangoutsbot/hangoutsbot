import sys, json, random, asyncio

import google
import wolframalpha
import wikipedia
import hangups
from hangups.ui.utils import get_conv_name

from hangupsbot.utils import text_to_segments

WOLFRAM_APPID = "E362PK-7395YTX894"
JOKES_PATH = "/home/cena/.local/share/hangupsbot/jokes.txt"
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
    """Unknown command handler"""
    bot.send_message(event.conv,
                     '{}: Un-recognized command!'.format(event.user.full_name))


@command.register
def help(bot, event, cmd=None, *args):
    """Help me, Obi-Wan Kenobi. You're my only hope."""
    if not cmd:
        segments = [hangups.ChatMessageSegment('Supported commands:', is_bold=True),
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
    """Play ping pong!"""
    bot.send_message(event.conv, 'pong')


@command.register
def echo(bot, event, *args):
    """Echo message"""
    bot.send_message(event.conv, '{}'.format(' '.join(args)))


@command.register
def users(bot, event, *args):
    """List all users"""
    segments = [hangups.ChatMessageSegment('User lists (total {}):'.format(len(event.conv.users)),
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
    """Search for users by name"""
    username_lower = username.strip().lower()
    segments = [hangups.ChatMessageSegment('Search results on behalf of users "{}":'.format(username),
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
    """List all active hangouts
        c: commands, f: forwarding, a: autoreplies"""
    segments = [hangups.ChatMessageSegment('List of active hangouts:', is_bold=True),
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
    """Rename Hangout"""
    yield from bot._client.setchatname(event.conv_id, ' '.join(args))


@command.register
def leave(bot, event, conversation=None, *args):
    """Exit Hangout"""
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
        yield from bot._conv_list.delete_conversation(c.id_)


@command.register
def easteregg(bot, event, easteregg, eggcount=1, period=0.5, *args):
    """Starts combo Easter eggs (parametrs:  easteregg, eggcount=1, period=0.5)
       Supported Easter eggs: ponies, pitchforks, bikeshed, shydino"""
    for i in range(int(eggcount)):
        yield from bot._client.sendeasteregg(event.conv_id, easteregg)
        if int(eggcount) > 1:
            yield from asyncio.sleep(float(period) + random.uniform(-0.1, 0.1))

@command.register
def spoof(bot, event, *args):
    """Spoof report"""
    segments = [hangups.ChatMessageSegment('!!! Caution !!!', is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
    segments.append(hangups.ChatMessageSegment('User {} ('.format(event.user.full_name)))
    link = 'https://plus.google.com/u/0/{}/about'.format(event.user.id_.chat_id)
    segments.append(hangups.ChatMessageSegment(link, hangups.SegmentType.LINK,
                                               link_target=link))
    segments.append(hangups.ChatMessageSegment(') has just been reported for attempted spoofing!'))
    bot.send_message_segments(event.conv, segments)


@command.register
def reload(bot, event, *args):
    """Reload config"""
    bot.config.load()

#My commands
@command.register
def joke(bot, event, *args):
    """Send joke!"""
    a_joke =str(random.choice(list(open(JOKES_PATH))))
    bot.send_message(event.conv, a_joke)


@command.register
def wiki(bot, event, *args):
    """Search query in wolfram!"""
    wiki_query = '{}'.format(' '.join(args))
    bot.send_message(event.conv, 'Computing with Wikpedia on {}'.format(wiki_query))
    
    try:
        wiki_res =  wikipedia.summary(wiki_query)
        bot.send_message(event.conv, wiki_res)
    except wikipedia.exceptions.DisambiguationError as e:
        text_res = 'Disambiguation result: {}'.format(str(e.options))
        bot.send_message(event.conv, text_res)
    except wikipedia.exceptions.PageError:
        text_res = 'No result.'
        bot.send_message(event.conv, text_res)
        

    

@command.register
def wolf(bot, event, *args):
    """Search query in wolfram!"""
    bot.send_message(event.conv, 'Computing with WolframAlpha on {}'.format(' '.join(args)))
    client = wolframalpha.Client(WOLFRAM_APPID)
    res = client.query('{}'.format(' '.join(args)))
    if len(list(res.results)) > 0:
        text_res = next(res.results).text
    else:
        text_res = "No result."
    bot.send_message(event.conv, text_res)

#My commands end

@command.register
def quit(bot, event, *args):
    """Quit bot"""
    print('HangupsBot killed by user {} from conversation {}'.format(event.user.full_name,
                                                                     get_conv_name(event.conv, truncate=True)))
    yield from bot._client.disconnect()


@command.register
def config(bot, event, cmd=None, *args):
    """Displays or modifies the configuratio file
        Parametrs: /bot config [get|set] [key] [subkey] [...] [value]"""

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
