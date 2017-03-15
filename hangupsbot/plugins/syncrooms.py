import aiohttp, asyncio, io, logging, os, time

import hangups

import plugins


logger = logging.getLogger(__name__)


class __registers(object):
    def __init__(self):
        self.last_event_id = '' # recorded last event to avoid re-syncing
        self.last_user_id = '' # recorded last user to allow message compression
        self.last_chatroom_id = '' # recorded last chat room to prevent room crossover
        self.last_time_id = 0 # recorded timestamp of last chat to 'expire' chats


_registers=__registers()


def _initialise(bot):
    _migrate_syncroom_v1(bot)

    plugins.register_handler(_broadcast, type="sending")
    plugins.register_handler(_repeat, type="allmessages")

    #_register_chatbridge_behaviour('userlist', _syncout_users)

    plugins.register_admin_command(["syncusers"])

    return []

    plugins.register_handler(_handle_syncrooms_membership_change, type="membership")


def _migrate_syncroom_v1(bot):
    if bot.config.exists(["conversations"]):
        write_config = False
        _config2 = []
        _newdict = {}
        _oldlist = bot.config.get_by_path(["conversations"])
        for conv_id in _oldlist:
            parameters = _oldlist[conv_id]
            if "sync_rooms" in parameters:
                old_sync_rooms = parameters["sync_rooms"]
                old_sync_rooms.append(conv_id)
                old_sync_rooms = list(set(old_sync_rooms))
                old_sync_rooms.sort()
                ref_key = "-".join(old_sync_rooms)
                _newdict[ref_key] = old_sync_rooms # prevent duplicates

                del parameters["sync_rooms"] # remove old config
                bot.config.set_by_path(["conversations", conv_id], parameters)
                write_config = True

        if write_config:
            _config2 = list(_newdict.values())
            bot.config.set_by_path(["sync_rooms"], _config2) # write new config
            bot.config.save()
            logger.info("_migrate_syncroom_v1(): config-v2 = {}".format(_config2))


@asyncio.coroutine
def _broadcast(bot, broadcast_list, context):
    target_conv_id = broadcast_list[0][0]
    message = broadcast_list[0][1]
    image_id = broadcast_list[0][2]

    if not bot.get_config_option('syncing_enabled'):
        return

    syncouts = bot.get_config_option('sync_rooms') or []
    syncout = False
    for sync_room_list in syncouts:
        if target_conv_id in sync_room_list:
            syncout = sync_room_list
            break
    if not syncout:
        return

    passthru = context["passthru"]

    if "norelay" not in passthru:
        passthru["norelay"] = []
    if __name__ in passthru["norelay"]:
        # prevent message broadcast duplication
        logger.info("NORELAY:_broadcast {}".format(passthru["norelay"]))
        return
    else:
        # halt messaging handler from re-relaying
        passthru["norelay"].append(__name__)

    myself = bot.user_self()
    chat_id = myself['chat_id']
    fullname = myself['full_name']

    if "original_request" in passthru:
        message = passthru["original_request"]["message"]
        image_id = passthru["original_request"]["image_id"]
        segments = passthru["original_request"]["segments"]
        if "user" in passthru["original_request"]:
            if(isinstance(passthru["original_request"]["user"], str)):
                message = "{}: {}".format(passthru["original_request"]["user"], message)
            else:
                chat_id = passthru["original_request"]["user"].id_.chat_id
                # message line formatting: required since hangouts is limited
                full_name = passthru["original_request"]["user"].full_name
                message = "{}: {}".format(full_name, message)

    # for messages from other plugins, relay them
    for relay_id in syncout:
        if target_conv_id != relay_id:
            logger.info("BROADCASTING: {} - {}".format(message, passthru))
            yield from bot.coro_send_message(
                relay_id,
                message,
                image_id = image_id,
                context = { "passthru": passthru })


@asyncio.coroutine
def _repeat(bot, event, command):
    """
    RELAY:
    * user messages
    * bot-wrapped user messages relayed by other chatbridges
    * bot messages from other plugins
    DO NOT RELAY:
    * bot-wrapped user messages relayed by this chatbridge
    """

    if not bot.get_config_option('syncing_enabled'):
        return

    syncouts = bot.get_config_option('sync_rooms') or []
    syncout = False
    for sync_room_list in syncouts:
        if event.conv_id in sync_room_list:
            syncout = sync_room_list
            break
    if not syncout:
        return

    passthru = event.passthru

    if "norelay" not in passthru:
        passthru["norelay"] = []
    if __name__ in passthru["norelay"]:
        # prevent message relay duplication
        logger.info("NORELAY:_repeat {}".format(passthru["norelay"]))
        return
    else:
        # halt sending handler from re-relaying
        passthru["norelay"].append(__name__)

    user = event.user
    message = event.text
    image_id = None

    if "original_request" in passthru:
        message = passthru["original_request"]["message"]
        image_id = passthru["original_request"]["image_id"]
        segments = passthru["original_request"]["segments"]
        # user is only assigned once, upon the initial event
        if "user" in passthru["original_request"]:
            user = passthru["original_request"]["user"]
        else:
            passthru["original_request"]["user"] = user
    else:
        # user raised an event
        passthru["original_request"] = { "message": event.text,
                                         "image_id": None, # XXX: should be attachments
                                         "segments": event.conv_event.segments,
                                         "user": event.user }

    # relay messages to other rooms only
    for relay_id in syncout:
        if event.conv_id != relay_id:
            logger.info("REPEATING: {} - {}".format(message, passthru))
            yield from bot.coro_send_message(
                relay_id,
                message = "{}: {}".format(event.user.full_name, message),
                image_id = image_id,
                context = { "passthru": passthru })


def _format_source(bot, user_id):
    user = bot.get_hangups_user(user_id)

    link = 'https://plus.google.com/u/0/{}/about'.format(user.id_.chat_id)
    try:
        fullname = '{0}'.format(user.full_name.split(' ', 1)[0])
        nickname = bot.get_memory_suboption(user.id_.chat_id, 'nickname')
        if nickname:
            fullname += " (" + nickname + ")"
    except TypeError:
        fullname = event.user.full_name

    html_identity = '**{}**'.format(fullname)

    return html_identity


def _register_chatbridge_behaviour(behaviour, object):
    try:
        chatbridge_behaviours = plugins.call_shared("chatbridge.behaviours")
    except KeyError:
        raise RuntimeException("handler does not seem to support chatbridge.behaviours")

    if __name__ not in chatbridge_behaviours:
        chatbridge_behaviours[__name__] = {}

    chatbridge_behaviours[__name__][behaviour] = object


def _syncout_users(bot, conv_id):
    if not bot.get_config_option('syncing_enabled'):
        return

    syncouts = bot.get_config_option('sync_rooms') or []
    syncout = False
    for sync_room_list in syncouts:
        if conv_id in sync_room_list:
            syncout = sync_room_list
            break
    if not syncout:
        return

    # generate by rooms list and all (*) list
    users = {"*" : {}}
    for room_id in syncout:
        users[room_id] = bot.get_users_in_conversation(room_id)
        for user in users[room_id]:
            users["*"][user.id_.chat_id] = user

    return users


@asyncio.coroutine
def _handle_syncrooms_membership_change(bot, event, command):
    if not bot.get_config_option('syncing_enabled'):
        return

    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return

    syncouts = bot.get_config_option('sync_rooms')

    if not syncouts:
        return # Sync rooms not configured, returning

    # are we in a sync room?
    sync_room_list = None
    for _rooms in syncouts:
        if event.conv_id in _rooms:
            sync_room_list = _rooms
            break
    if sync_room_list is None:
        return

    # Generate list of added or removed users for current ROOM

    event_users = [bot.get_hangups_user(user_id) for user_id
                   in event.conv_event.participant_ids]
    names = ', '.join([user.full_name for user in event_users])

    syncroom_name = '<b>' + bot.conversations.get_name(event.conv) + '</b>'

    if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        # JOIN a specific room

        logger.info("{} user(s) added to {}".format(len(event_users), event.conv_id))

        if syncroom_name:
            yield from bot.coro_send_message(event.conv, '<i>{} has added {} to {}</i>'.format(
                event.user.full_name,
                names,
                syncroom_name))
    else:
        # LEAVE a specific room

        logger.info("{} user(s) left {}".format(len(event_users), event.conv_id))

        if syncroom_name:
            yield from bot.coro_send_message(event.conv, '<i>{} has left {}</i>'.format(
                names,
                syncroom_name))


def syncusers(bot, event, *args):
    """syncroom-aware users list.
    optional parameter conversation_id to get a list of users in other rooms. will include users
    in linked syncrooms. append "rooms" to segment user list by individual rooms.
    """
    if not bot.get_config_option('syncing_enabled'):
        return

    combined = True

    tokens = list(args)
    if "rooms" in args:
        tokens.remove("rooms")
        combined = False
    if "rooms" in args:
        tokens.remove("room")
        combined = False

    if len(args) == 0:
        filter_convs = [ event.conv_id ]
    else:
        filter_convs = tokens

    target_conv = filter_convs.pop(0)

    user_lists = _syncout_users(bot, target_conv)
    if not user_lists:
        yield from bot.coro_send_message(event.conv_id, "no users were returned")
        return

    _lines = []

    for room_id in user_lists:
        if combined and room_id != "*":
            # list everything, only use wildcard
            continue
        elif not combined and room_id == "*":
            # list room-by-room, skip wildcard
            continue

        if filter_convs and room_id not in filter_conv and room_id != target_conv:
            # if >1 conv id provided, filter by only supplied conv ids
            continue

        if room_id == "*":
            _lines.append("**all syncout rooms**")
        else:
            _lines.append("**{} ({})**".format( bot.conversations.get_name(room_id),
                                                room_id ))

        user_list = user_lists[room_id]
        for chat_id in user_list:
            _lines.append("* {}".format(user_list[chat_id].full_name))

    yield from bot.coro_send_message(event.conv_id, "\n".join(_lines))

    """
    # are we in a sync room?
    sync_room_list = None
    for _rooms in syncouts:
        if conversation_id in _rooms:
            sync_room_list = _rooms
            _lines.append(_("<b>Sync Rooms: {}</b>").format(len(sync_room_list)))
            break
    if sync_room_list is None:
        sync_room_list = [conversation_id]
        _lines.append(_("<b>Standard Room</b>"))

    all_users = {}
    try:
        if combined or len(sync_room_list) == 1:
            all_users["_ALL_"] = bot.get_users_in_conversation(sync_room_list)
        else:
            for room_id in sync_room_list:
                all_users[room_id] = bot.get_users_in_conversation(room_id)
    except KeyError as e:
        # most likely raised if user provides invalid room list
        yield from bot.coro_send_message(event.conv, _('<b>failed to retrieve user list</b>'))
        return

    unique_users = []

    for room_id in all_users:
        if room_id is not "_ALL_":
            _line_room = '<i>{}</i>'.format(room_id)
            _line_room = '<b>{}</b> {}'.format(
                bot.conversations.get_name(room_id),
                _line_room)
            _lines.append(_line_room)
        list_users = all_users[room_id]
        for User in list_users:
            _line_user = '{}'.format(User.full_name);
            if User.emails:
                _line_user = _line_user + ' ({})'.format(User.emails[0])
            _lines.append(_line_user)
            unique_users.append(User)

    unique_users = list(set(unique_users))
    _lines.append(_("<b>Total Unique: {}</b>").format(len(unique_users)))

    yield from bot.coro_send_message(event.conv, '<br />'.join(_lines))
    """