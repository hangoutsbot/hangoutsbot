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

    return []

    plugins.register_admin_command(["syncusers"])
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


def _broadcast(bot, broadcast_list, context):
    """
    RELAY:
    * bot messages from other plugins
    DO NOT RELAY:
    * any messages already relayed by this plugin
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

    destination_conv_id = broadcast_list[0][0]
    message = broadcast_list[0][1]

    passthru = context["passthru"]
    if passthru and "sourceplugin" in passthru and passthru['sourceplugin'] == __name__:
        # no further processing required for messages being relayed by same plugin
        return

    for relay_id in syncout:
        if destination_conv_id != relay_id:
            # for messages from other sources, relay them
            yield from bot.coro_send_message(
                relay_id,
                "POST-RELAYED: {}".format(message),
                context = { "passthru": { "sourceplugin" : __name__,
                                          "sourcegroup" : destination_conv_id }})


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
    if passthru and "sourceplugin" in passthru and passthru["sourceplugin"] == __name__:
        # don't repeat messages that originate from the same plugin
        return

    for relay_id in syncout:
        if event.conv_id != relay_id:
            # relay messages to other rooms only
            yield from bot.coro_send_message(
                relay_id,
                _format_source(bot, event.user_id.chat_id) + ": " + event.text,
                context = { "passthru": { "sourceplugin" : __name__,
                                          "sourcegroup" : event.conv_id }})


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

    html_identity = '<b><a href="{}">{}</a></b>'.format(link, fullname)

    return html_identity


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


def syncusers(bot, event, conversation_id=None, *args):
    """syncroom-aware users list.
    optional parameter conversation_id to get a list of users in other rooms. will include users
    in linked syncrooms. append "rooms" to segment user list by individual rooms.
    """
    combined = True

    if not conversation_id:
        conversation_id = event.conv_id
    elif conversation_id == "rooms":
        # user specified /bot syncusers rooms
        conversation_id = event.conv_id
        combined = False

    if "rooms" in args:
        # user specified /bot syncusers [roomid] rooms
        combined = False

    syncouts = bot.get_config_option('sync_rooms')

    if not syncouts:
        return # Sync rooms not configured, returning

    _lines = []

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
