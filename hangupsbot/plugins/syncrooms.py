import asyncio, re, time

import goslate
import hangups

from hangups.ui.utils import get_conv_name

gs = goslate.Goslate()

class __registers(object):
    def __init__(self):
        self.last_event_id = '' # recorded last event to avoid re-syncing
        self.last_user_id = '' # recorded last user to allow message compression
        self.last_chatroom_id = '' # recorded last chat room to prevent room crossover
        self.last_time_id = 0 # recorded timestamp of last chat to 'expire' chats

_registers=__registers()

def _initialise(Handlers, bot=None):
    _migrate_syncroom_v1(bot)
    Handlers.register_handler(_handle_syncrooms_broadcast, type="sending")
    Handlers.register_handler(_handle_incoming_message, type="message")
    Handlers.register_handler(_handle_syncrooms_membership_change, type="membership")
    return ['synclanguage'] # implements no commands

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
            print("_migrate_syncroom_v1(): config-v2 = {}".format(_config2))

def _handle_syncrooms_broadcast(bot, broadcast_list, context):
    if not bot.get_config_option('syncing_enabled'):
        return

    if context is "no_syncrooms_handler":
        print("SYNCROOMS: handler disabled by context")
        return

    origin_conversation_id = broadcast_list[0][0]
    response = broadcast_list[0][1]

    syncouts = bot.get_config_option('sync_rooms')
    if syncouts:
        for sync_room_list in syncouts:
            if origin_conversation_id in sync_room_list:
                for other_room_id in sync_room_list:
                    if origin_conversation_id != other_room_id:
                        broadcast_list.append((other_room_id, response))

                print("SYNCROOMS: broadcasting to {} room(s)".format(
                    len(broadcast_list)))
            else:
                print("SYNCROOMS: not a sync room".format(origin_conversation_id))


@asyncio.coroutine
def _handle_incoming_message(bot, event, command):
    """Handle message syncing"""
    if not bot.get_config_option('syncing_enabled'):
        return

    syncouts = bot.get_config_option('sync_rooms')

    if not syncouts:
        return # Sync rooms not configured, returning

    if _registers.last_event_id == event.conv_event.id_:
        return # This event has already been synced

    _registers.last_event_id = event.conv_event.id_

    for sync_room_list in syncouts:
        if event.conv_id in sync_room_list:
            print('SYNCROOMS: incoming message');
            link = 'https://plus.google.com/u/0/{}/about'.format(event.user_id.chat_id)

            ### Deciding how to relay the name across

            # Checking that it hasn't timed out since last message
            timeout_threshold = 30.0 # Number of seconds to allow the timeout
            if time.time() - _registers.last_time_id > timeout_threshold:
                timeout = True
            else:
                timeout = False

            # Checking if the user is the same as the one who sent the previous message
            if _registers.last_user_id in event.user_id.chat_id:
                sameuser = True
            else:
                sameuser = False

            # Checking if the room is the same as the room where the last message was sent
            if _registers.last_chatroom_id in event.conv_id:
                sameroom = True
            else:
                sameroom = False

            if (not sameroom or timeout or not sameuser) and \
                (bot.memory.exists(['user_data', event.user_id.chat_id, "nickname"])):
                # Now check if there is a nickname set

                try:
                    fullname = '{0} ({1})'.format(event.user.full_name.split(' ', 1)[0]
                        , bot.get_memory_suboption(event.user_id.chat_id, 'nickname'))
                except TypeError:
                    fullname = event.user.full_name
            elif sameroom and sameuser and not timeout:
                fullname = '>>'
            else:
                fullname = event.user.full_name

            ### Name decided and put into variable 'fullname'

            segments = [hangups.ChatMessageSegment('{0}'.format(fullname), hangups.SegmentType.LINK,
                                                   link_target=link, is_bold=True),
                        hangups.ChatMessageSegment(': ', is_bold=True)]

            # Append links to attachments (G+ photos) to forwarded message
            if event.conv_event.attachments:
                segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
                segments.extend([hangups.ChatMessageSegment(link, hangups.SegmentType.LINK, link_target=link)
                                 for link in event.conv_event.attachments])

            # Make links hyperlinks and send message
            URL_RE = re.compile(r'https?://\S+')
            for segment in event.conv_event.segments:
                last = 0
                for match in URL_RE.finditer(segment.text):
                    if match.start() > last:
                        segments.append(hangups.ChatMessageSegment(segment.text[last:match.start()]))
                    segments.append(hangups.ChatMessageSegment(match.group(), link_target=match.group()))
                    last = match.end()
                if last != len(segment.text):
                    segments.append(hangups.ChatMessageSegment(segment.text[last:]))

            origin_language = _get_syncroom_language(bot, event.conv_id)

            for _conv_id in sync_room_list:
                if not _conv_id == event.conv_id:

                    cloned_segments = list(segments) # we need this for multi-language

                    target_language = _get_syncroom_language(bot, _conv_id)
                    if origin_language != target_language:
                        translated = gs.translate(event.text, target_language)
                        if event.text != translated:
                            cloned_segments.extend([
                                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                                hangups.ChatMessageSegment('(' + translated + ')')])

                    bot.send_message_segments(_conv_id, cloned_segments, context="no_syncrooms_handler")

            _registers.last_user_id = event.user_id.chat_id
            _registers.last_time_id = time.time()
            _registers.last_chatroom_id = event.conv_id

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

    # Generate list of added or removed users
    event_users = [event.conv.get_user(user_id) for user_id
                   in event.conv_event.participant_ids]
    names = ', '.join([user.full_name for user in event_users])

    # JOIN
    if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        print("SYNCROOMS: members added")
        bot.send_message(event.conv, '{} has added {} to the Syncout'.format(event.user.full_name, names))
    # LEAVE
    else:
        print("SYNCROOMS: members left")
        bot.send_message(event.conv, '{} has left the Syncout'.format(names))


def _get_syncroom_language(bot, conversation_id, default="en"):
    syncroom_language = bot.conversation_memory_get(conversation_id, 'syncroom_language')
    if syncroom_language is None:
        return default
    else:
        return syncroom_language


def synclanguage(bot, event, iso_language=None, *args):
    language_map = gs.get_languages()

    if iso_language is None:
        bot.send_message_parsed(
            event.conv,
            '<i>syncroom "{}" language is {}</i>'.format(
                get_conv_name(event.conv),
                language_map[_get_syncroom_language(bot, event.conv_id)]))

    if iso_language in language_map:
        text_language = language_map[iso_language]

        bot.conversation_memory_set(event.conv_id, 'syncroom_language', iso_language)

        bot.send_message_parsed(
            event.conv,
            '<i>syncroom "{}" language set to {}</i>'.format(
                get_conv_name(event.conv),
                text_language))