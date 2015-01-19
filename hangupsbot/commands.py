import sys, json, random, asyncio, logging, os

import hangups
from hangups.ui.utils import get_conv_name

from utils import text_to_segments

from pushbullet import PushBullet

draw_lists = {}
import re
from random import shuffle

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

    """minimum length check for @mention"""
    username = args[0].strip()
    if len(username) <= 2:
        logging.warning("@mention from {} ({}) too short (== '{}')".format(event.user.full_name, event.user.id_.chat_id, username))
        return

    """check if synced room"""
    if event.conv_id in bot.get_config_option('sync_rooms'):
        syncout = True
    else:
        syncout = False

    """
    /bot mention <fragment> test
    """
    noisy_mention_test = False
    if len(args) == 2 and args[1] == "test":
        noisy_mention_test = True

    """
    quidproquo: users can only @mention if they themselves are @mentionable (i.e. have a 1-on-1 with the bot)
    """
    conv_1on1_initiator = None
    if bot.get_config_option("mentionquidproquo"):
        conv_1on1_initiator = bot.get_1on1_conversation(event.user.id_.chat_id)
        if conv_1on1_initiator:
            logging.info("quidproquo: user {} ({}) has 1-on-1".format(event.user.full_name, event.user.id_.chat_id))
        else:
            logging.warning("quidproquo: user {} ({}) has no 1-on-1".format(event.user.full_name, event.user.id_.chat_id))
            if noisy_mention_test or bot.get_config_suboption(event.conv_id, 'mentionerrors'):
                bot.send_message_parsed(
                    event.conv,
                    "<b>{}</b> cannot @mention anyone until they say something to me first.".format(
                        event.user.full_name))
            return

    """track mention statistics"""
    user_tracking = {
      "mentioned":[],
      "ignored":[],
      "failed": {
        "pushbullet": [],
        "one2one": [],
      }
    }

    """
    begin mentioning users as long as they exist in the current conversation...
    """

    conversation_name = get_conv_name(event.conv, truncate=True);
    logging.info("@mention '{}' in '{}' ({})".format(username, conversation_name, event.conv.id_))
    username_lower = username.lower()

    """is @all available globally/per-conversation/initiator?"""
    if username_lower == "all":
        if not bot.get_config_suboption(event.conv.id_, 'mentionall'):

            """global toggle is off/not set, check admins"""
            logging.info("@all in {}: disabled/unset global/per-conversation".format(event.conv.id_))
            admins_list = bot.get_config_suboption(event.conv_id, 'admins')
            if event.user_id.chat_id not in admins_list:

                """initiator is not an admin, check whitelist"""
                logging.info("@all in {}: user {} ({}) is not admin".format(event.conv.id_, event.user.full_name, event.user.id_.chat_id))
                all_whitelist = bot.get_config_suboption(event.conv_id, 'allwhitelist')
                if all_whitelist is None or event.user_id.chat_id not in all_whitelist:

                    logging.warning("@all in {}: user {} ({}) blocked".format(event.conv.id_, event.user.full_name, event.user.id_.chat_id))
                    if conv_1on1_initiator:
                        bot.send_message_parsed(
                            conv_1on1_initiator,
                            "You are not allowed to use @all in <b>{}</b>".format(
                                conversation_name))
                    if noisy_mention_test or bot.get_config_suboption(event.conv_id, 'mentionerrors'):
                        bot.send_message_parsed(
                            event.conv,
                            "<b>{}</b> blocked from using <i>@all</i>".format(
                                event.user.full_name))
                    return
                else:
                    logging.info("@all in {}: allowed, {} ({}) is whitelisted".format(event.conv.id_, event.user.full_name, event.user.id_.chat_id))
            else:
                logging.info("@all in {}: allowed, {} ({}) is an admin".format(event.conv.id_, event.user.full_name, event.user.id_.chat_id))
        else:
            logging.info("@all in {}: enabled global/per-conversation".format(event.conv.id_))

    for u in event.conv.users:
        if username_lower == "all" or \
                username_lower in u.full_name.replace(" ", "").lower():

            logging.info("user {} ({}) is present".format(u.full_name, u.id_.chat_id))

            if u.is_self:
                """bot cannot be @mentioned"""
                logging.info("suppressing bot mention by {} ({})".format(event.user.full_name, event.user.id_.chat_id))
                continue

            if u.id_.chat_id == event.user.id_.chat_id and username_lower == "all":
                """prevent initiating user from receiving duplicate @all"""
                logging.info("suppressing @all for {} ({})".format(event.user.full_name, event.user.id_.chat_id))
                continue

            donotdisturb = bot.config.get('donotdisturb')
            if donotdisturb:
                """user-configured DND"""
                if u.id_.chat_id in donotdisturb:
                    logging.info("suppressing @mention for {} ({})".format(u.full_name, u.id_.chat_id))
                    user_tracking["ignored"].append(u.full_name)
                    continue

            alert_via_1on1 = True

            """pushbullet integration"""
            pushbullet_integration = bot.get_config_suboption(event.conv.id_, 'pushbullet')
            if pushbullet_integration is not None:
                if u.id_.chat_id in pushbullet_integration.keys():
                    pushbullet_config = pushbullet_integration[u.id_.chat_id]
                    if pushbullet_config["api"] is not None:
                        pb = PushBullet(pushbullet_config["api"])
                        success, push = pb.push_note(
                            "{} mentioned you in {}".format(
                                event.user.full_name,
                                conversation_name,
                                event.text))
                        if success:
                            user_tracking["mentioned"].append(u.full_name)
                            logging.info("{} ({}) alerted via pushbullet".format(u.full_name, u.id_.chat_id))
                            alert_via_1on1 = False # disable 1on1 alert
                        else:
                            user_tracking["failed"]["pushbullet"].append(u.full_name)
                            logging.warning("pushbullet alert failed for {} ({})".format(u.full_name, u.id_.chat_id))

            if alert_via_1on1:
                """send alert with 1on1 conversation"""
                conv_1on1 = bot.get_1on1_conversation(u.id_.chat_id)
                if conv_1on1:
                    bot.send_message_parsed(
                        conv_1on1,
                        "<b>{}</b> @mentioned you in <i>{}</i>:<br />{}".format(
                            event.user.full_name,
                            conversation_name,
                            event.text))
                    user_tracking["mentioned"].append(u.full_name)
                    logging.info("{} ({}) alerted via 1on1 ({})".format(u.full_name, u.id_.chat_id, conv_1on1.id_))
                else:
                    user_tracking["failed"]["one2one"].append(u.full_name)
                    if bot.get_config_suboption(event.conv_id, 'mentionerrors'):
                        bot.send_message_parsed(
                            event.conv,
                            "@mention didn't work for <b>{}</b>. User must say something to me first.".format(
                                u.full_name))
                    logging.warning("user {} ({}) could not be alerted via 1on1".format(u.full_name, u.id_.chat_id))

    if noisy_mention_test:
        html = "<b>@mentions:</b><br />"
        if len(user_tracking["failed"]["one2one"]) > 0:
            html = html + "1-to-1 fail: <i>{}</i><br />".format(", ".join(user_tracking["failed"]["one2one"]))
        if len(user_tracking["failed"]["pushbullet"]) > 0:
            html = html + "PushBullet fail: <i>{}</i><br />".format(", ".join(user_tracking["failed"]["pushbullet"]))
        if len(user_tracking["ignored"]) > 0:
            html = html + "Ignored (DND): <i>{}</i><br />".format(", ".join(user_tracking["ignored"]))
        if len(user_tracking["mentioned"]) > 0:
            html = html + "Alerted: <i>{}</i><br />".format(", ".join(user_tracking["mentioned"]))
        else:
            html = html + "Nobody was successfully @mentioned ;-(<br />"

        if len(user_tracking["failed"]["one2one"]) > 0:
            html = html + "Users failing 1-to-1 need to say something to me privately first.<br />"

        bot.send_message_parsed(event.conv, html)

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
    """whoami: get user id"""

    if event.user_id.chat_id in bot.get_config_option('nickname'):
        if bot.get_config_option('nickname')[event.user_id.chat_id]['ign'] == '':
            fullname = event.user.full_name
        else:
            fullname = '{0} ({1})'.format(event.user.full_name
                , bot.get_config_option('nickname')[event.user_id.chat_id]['ign'])
    else:
        fullname = event.user.full_name

    bot.send_message_parsed(event.conv, "<b>{}</b>, chat_id = <i>{}</i>".format(fullname, event.user.id_.chat_id))

@command.register
def whereami(bot, event, *args):
    """whereami: get conversation id"""
    bot.send_message_parsed(
      event.conv,
      "You are at <b>{}</b>, conv_id = <i>{}</i>".format(
        get_conv_name(event.conv, truncate=True),
        event.conv.id_))

@command.register
def lookup(bot, event, *args):
    """find keywords in a specified spreadsheet"""

    if not bot.get_config_option('spreadsheet_enabled'):
        bot.send_message_parsed(event.conv, "Spreadsheet function disabled")
        return

    if not bot.get_config_option('spreadsheet_url'):
        bot.send_message_parsed(event.conv, "Spreadsheet URL not set")
        return

    if not bot.get_config_option('spreadsheet_table_class'):
        bot.send_message_parsed(event.conv, "Spreadsheet table identifier not set")
        return

    spreadsheet_url = bot.get_config_option('spreadsheet_url')
    table_class = bot.get_config_option('spreadsheet_table_class') # Name of table class to search

    keyword = ' '.join(args)

    segments = [hangups.ChatMessageSegment('Results for keyword "{}":'.format(keyword),
                                           is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
    print("{0} ({1}) has requested to lookup '{2}'".format(event.user.full_name, event.user.id_.chat_id, keyword))
    import urllib.request
    html = urllib.request.urlopen(spreadsheet_url).read()

    keyword_lower = keyword.strip().lower()

    data = []

    counter = 0
    counter_max = 5 # Maximum rows displayed per query

    # Adapted from http://stackoverflow.com/questions/23377533/python-beautifulsoup-parsing-table
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(str(html, 'utf-8'))
    table = soup.find('table', attrs={'class':table_class})
    table_body = table.find('tbody')

    rows = table_body.find_all('tr')

    for row in rows:
        col = row.find_all('td')
        cols = [ele.text.strip() for ele in col]
        data.append([ele for ele in cols if ele]) # Get rid of empty values

    for row in data:
        matchfound = 0
        for cell in row:
            testcell = str(cell).lower().strip()
            if (keyword_lower in testcell) and counter < counter_max and matchfound == 0:
                segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
                segments.append(hangups.ChatMessageSegment('Row {}: '.format(counter+1),
                                                       is_bold=True))
                for datapoint in row:
                    segments.append(hangups.ChatMessageSegment(datapoint))
                    segments.append(hangups.ChatMessageSegment(' | ', is_bold=True))
                segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
                counter += 1
                matchfound = 1
            elif (keyword_lower in testcell) and counter >= counter_max:
                counter += 1

    if counter > counter_max:
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
        segments.append(hangups.ChatMessageSegment('{0} rows found. Only returning first {1}.'.format(counter, counter_max), is_bold=True))
    if counter == 0:
        segments.append(hangups.ChatMessageSegment('No match found', is_bold=True))

    segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    bot.send_message_segments(event.conv, segments)


@command.register
def setnickname(bot, event, *args):
    """allow users to set a nickname for sync relay
        /bot setnickname <nickname>"""
    truncatelength = 16 # What should the maximum length of the nickname be?

    nickname = ' '.join(args).strip()[0:truncatelength]
    if(nickname == ''):
        bot.send_message_parsed(event.conv,"Removing nickname")
    else:
        bot.send_message_parsed(
            event.conv,
            "setting nickname to '{}'".format(nickname))
    bot.config.set_by_path(["nickname", event.user.id_.chat_id], { "ign": nickname })
    bot.config.save()

@command.register
def prepare(bot, event, *args):
    """prepares a bundle of things for a random draw
        /bot prepare numbers 1-8
            "numbers" = [1,2,3,4,5,6,7,8]
        /bot prepare numbers 42,74,98,3
            "numbers" = [42,74,98,3]
        /bot prepare sticks 3long1short
            "stick" = [long,long,long,short]
        /bot prepare 1-3
            "default" = [1,2,3]

        note: see /me draw for user lottery/drawings

        XXX: generated lists are NOT saved on bot termination
    """
    listname = "default"
    listdef = args[0]
    if len(args) == 2:
        listname = args[0]
        listdef = args[1]
    global_draw_name = event.conv.id_ + "-" + listname

    draw_lists[global_draw_name] = {"box": [], "users": {}}

    """special types
        /bot prepare [thing] COMPASS - 4 cardinal + 4 ordinal

        XXX: add more useful shortcuts here!
    """
    if listdef == "COMPASS":
        listdef = "north,north-east,east,south-east,south,south-west,west,north-west"

    # parse listdef

    if "," in listdef:
        # comma-separated single tokens
        draw_lists[global_draw_name]["box"] = listdef.split(",")

    elif re.match("\d+-\d+", listdef):
        # sequential range: <integer> to <integer>
        _range = listdef.split("-")
        min = int(_range[0])
        max = int(_range[1])
        if min == max:
            raise Exception("prepare: min and max are the same ({})".format(min))
        if max < min:
            min, max = max, min
        max = max + 1 # inclusive
        draw_lists[global_draw_name]["box"] = list(range(min, max))

    else:
        # numberTokens: <integer><name>
        pattern = re.compile("((\d+)([a-z\-_]+))", re.IGNORECASE)
        matches = pattern.findall(listdef)
        if len(matches) > 1:
            for tokendef in matches:
                tcount = int(tokendef[1])
                tname = tokendef[2]
                for i in range(0, tcount):
                    draw_lists[global_draw_name]["box"].append(tname)

        else:
            raise Exception("prepare: unrecognised match (!csv, !range, !numberToken): {}".format(listdef))

    if len(draw_lists[global_draw_name]["box"]) > 0:
        random.shuffle(draw_lists[global_draw_name]["box"])
        bot.send_message_parsed(
            event.conv,
            "The <b>{}</b> lottery is ready: {} items loaded and shuffled into the box.".format(listname, len(draw_lists[global_draw_name]["box"])))
    else:
        raise Exception("prepare: {} was initialised empty".format(global_draw_name))

@command.register
def perform_drawing(bot, event, *args):
    """draw handling:
        /me draw[s] [a[n]] number[s] => draws from "number", "numbers" or "numberes"
        /me draw[s] [a[n]] sticks[s] => draws from "stick", "sticks" or "stickses"
        /me draws[s]<unrecognised> => draws from "default"

        note: to prepare lotteries/drawings, see /bot prepare ...

        XXX: check is for singular, plural "-s" and plural "-es"
    """
    pattern = re.compile("/me draws?( +(a +|an +)?([a-z0-9\-_]+))?$", re.IGNORECASE)
    if pattern.match(event.text):
        listname = "default"

        matches = pattern.search(event.text)
        groups = matches.groups()
        if groups[2] is not None:
            listname = groups[2]

        # XXX: TOTALLY WRONG way to handle english plurals!
        # motivation: botmins prepare "THINGS" for a drawing, but users draw a (single) "THING"
        if listname.endswith("s"):
            _plurality = (listname[:-1], listname, listname + "es")
        else:
            _plurality = (listname, listname + "s", listname + "es")
        # seek a matching draw name based on the hacky english singular-plural spellings
        global_draw_name = None
        for word in _plurality:
            global_draw_name = event.conv.id_ + "-" + word
            if global_draw_name in draw_lists.keys():
                break

        if global_draw_name is not None:
            if len(draw_lists[global_draw_name]["box"]) > 0:
                if event.user.id_.chat_id in draw_lists[global_draw_name]["users"]:
                    # user already drew something from the box
                    bot.send_message_parsed(event.conv,
                        "<b>{}</b>, you have already drew <b>{}</b> from the <b>{}</b> box".format(
                            event.user.full_name,
                            draw_lists[global_draw_name]["users"][event.user.id_.chat_id],
                            word))

                else:
                    # draw something for the user
                    _thing = str(draw_lists[global_draw_name]["box"].pop())

                    text_drawn = "<b>{}</b> draws <b>{}</b> from the <b>{}</b> box. ".format(event.user.full_name, _thing, word, );
                    if len(draw_lists[global_draw_name]["box"]) == 0:
                        text_drawn = text_drawn + "...AAAAAND its all gone! The <b>{}</b> lottery is over folks.".format(word)

                    bot.send_message_parsed(event.conv, text_drawn)

                    draw_lists[global_draw_name]["users"][event.user.id_.chat_id] = _thing
            else:
                text_finished = "<b>{}</b>, the <b>{}</b> lottery is over. ".format(event.user.full_name, word);

                if event.user.id_.chat_id in draw_lists[global_draw_name]["users"]:
                    text_finished = "You drew a {} previously.".format(draw_lists[global_draw_name]["users"][event.user.id_.chat_id]);

                bot.send_message_parsed(event.conv, text_finished)
