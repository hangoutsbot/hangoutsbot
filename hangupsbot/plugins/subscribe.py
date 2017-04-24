import asyncio
import logging
import re
import sys

import plugins

from utils import remove_accents


logger = logging.getLogger(__name__)


class __internal_vars():
    def __init__(self):
        """ Cache to keep track of what keywords are being watched. Listed by user_id """
        self.keywords = {}

_internal = __internal_vars()


def _initialise():
    plugins.register_handler(_handle_keyword)
    plugins.register_user_command(["subscribe", "unsubscribe"])
    plugins.register_admin_command(["testsubscribe"])


def _handle_keyword(bot, event, command, include_event_user=False):
    """handle keyword"""
    if event.user.is_self:
        return

    _populate_keywords(bot, event)

    users_in_chat = event.conv.users

    """check if synced room and syncing is enabled
    if its a valid syncroom, get a list of all unique users across all rooms"""

    if bot.get_config_option('syncing_enabled'):
        syncouts = bot.get_config_option('sync_rooms') or []
        for sync_room_list in syncouts:
            if event.conv_id in sync_room_list:
                for syncedroom in sync_room_list:
                    if event.conv_id not in syncedroom:
                        users_in_chat += bot.get_users_in_conversation(syncedroom)
                users_in_chat = list(set(users_in_chat)) # make unique

    event_text = re.sub(r"\s+", " ", event.text)
    event_text_lower = event.text.lower()
    for user in users_in_chat:
        chat_id = user.id_.chat_id
        try:
            if _internal.keywords[chat_id] and ( not chat_id in event.user.id_.chat_id
                                                 or include_event_user ):
                for phrase in _internal.keywords[chat_id]:
                    regexphrase = r"(^|\b| )" + re.escape(phrase) + r"($|\b)"
                    if re.search(regexphrase, event_text, re.IGNORECASE):

                        """XXX: suppress alerts if it appears to be a valid mention to same user
                        logic condensed from the detection function in the mentions plugin, we may
                        miss some use-cases, but this should account for "most" of them"""
                        if 'plugins.mentions' in sys.modules:
                            _phrase_lower = phrase.lower()
                            _mention = "@" + _phrase_lower
                            if (_mention + " ") in event_text_lower or event_text_lower.endswith(_mention):
                                user = bot.get_hangups_user(chat_id)
                                _normalised_full_name_lower = remove_accents(user.full_name.lower())
                                if( _phrase_lower in _normalised_full_name_lower
                                        or _phrase_lower in _normalised_full_name_lower.replace(" ", "")
                                        or _phrase_lower in _normalised_full_name_lower.replace(" ", "_") ):
                                    # part of name mention: skip
                                    logger.debug("subscription matched full name fragment {}, skipping".format(user.full_name))
                                    continue
                                if bot.memory.exists(['user_data', chat_id, "nickname"]):
                                    _nickname = bot.memory.get_by_path(['user_data', chat_id, "nickname"])
                                    if _phrase_lower == _nickname.lower():
                                        # nickname mention: skip
                                        logger.debug("subscription matched exact nickname {}, skipping".format(_nickname))
                                        continue

                        yield from _send_notification(bot, event, phrase, user)
        except KeyError:
            # User probably hasn't subscribed to anything
            continue


def _populate_keywords(bot, event):
    # Pull the keywords from file if not already
    if not _internal.keywords:
        bot.initialise_memory(event.user.id_.chat_id, "user_data")
        for userchatid in bot.memory.get_option("user_data"):
            userkeywords = []
            if bot.memory.exists(["user_data", userchatid, "keywords"]):
                userkeywords = bot.memory.get_by_path(["user_data", userchatid, "keywords"])

            if userkeywords:
                _internal.keywords[userchatid] = userkeywords
            else:
                _internal.keywords[userchatid] = []


@asyncio.coroutine
def _send_notification(bot, event, phrase, user):
    """Alert a user that a keyword that they subscribed to has been used"""

    conversation_name = bot.conversations.get_name(event.conv)
    logger.info("keyword '{}' in '{}' ({})".format(phrase, conversation_name, event.conv.id_))

    """support for reprocessor
    override the source name by defining event._external_source"""
    source_name = event.user.full_name
    if hasattr(event, '_external_source'):
        source_name = event._external_source

    """send alert with 1on1 conversation"""
    conv_1on1 = yield from bot.get_1to1(user.id_.chat_id, context={ 'initiator_convid': event.conv_id })
    if conv_1on1:
        try:
            user_has_dnd = bot.call_shared("dnd.user_check", user.id_.chat_id)
        except KeyError:
            user_has_dnd = False
        if not user_has_dnd: # shared dnd check
            yield from bot.coro_send_message(
                conv_1on1,
                _("<b>{}</b> mentioned '{}' in <i>{}</i>:<br />{}").format(
                    source_name,
                    phrase,
                    conversation_name,
                    event.text))
            logger.info("{} ({}) alerted via 1on1 ({})".format(user.full_name, user.id_.chat_id, conv_1on1.id_))
        else:
            logger.info("{} ({}) has dnd".format(user.full_name, user.id_.chat_id))
    else:
        logger.warning("user {} ({}) could not be alerted via 1on1".format(user.full_name, user.id_.chat_id))


def subscribe(bot, event, *args):
    """allow users to subscribe to phrases, only one input at a time"""
    _populate_keywords(bot, event)

    keyword = ' '.join(args).strip().lower()
    keyword = re.sub(r"\s+", " ", keyword)

    conv_1on1 = yield from bot.get_1to1(event.user.id_.chat_id)
    if not conv_1on1:
        yield from bot.coro_send_message(
            event.conv,
            _("Note: I am unable to ping you until you start a 1 on 1 conversation with me!"))

    if not keyword:
        yield from bot.coro_send_message(
            event.conv,_("Usage: /bot subscribe [keyword]"))
        if _internal.keywords[event.user.id_.chat_id]:
            yield from bot.coro_send_message(
                event.conv,
                _("Subscribed to: {}").format(', '.join(_internal.keywords[event.user.id_.chat_id])))
        return

    if event.user.id_.chat_id in _internal.keywords:
        if keyword in _internal.keywords[event.user.id_.chat_id]:
            # Duplicate!
            yield from bot.coro_send_message(
                event.conv,_("Already subscribed to '{}'!").format(keyword))
            return
        else:
            # Not a duplicate, proceeding
            if not _internal.keywords[event.user.id_.chat_id]:
                # First keyword!
                _internal.keywords[event.user.id_.chat_id] = [keyword]
                yield from bot.coro_send_message(
                    event.conv,
                    _("Note: You will not be able to trigger your own subscriptions. To test, please ask somebody else to test this for you."))
            else:
                # Not the first keyword!
                _internal.keywords[event.user.id_.chat_id].append(keyword)
    else:
        _internal.keywords[event.user.id_.chat_id] = [keyword]
        yield from bot.coro_send_message(
            event.conv,
            _("Note: You will not be able to trigger your own subscriptions. To test, please ask somebody else to test this for you."))


    # Save to file
    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "keywords"], _internal.keywords[event.user.id_.chat_id])
    bot.memory.save()

    yield from bot.coro_send_message(
        event.conv,
        _("Subscribed to: {}").format(', '.join(_internal.keywords[event.user.id_.chat_id])))


def unsubscribe(bot, event, *args):
    """Allow users to unsubscribe from phrases"""
    _populate_keywords(bot, event)

    keyword = ' '.join(args).strip().lower()
    keyword = re.sub(r"\s+", " ", keyword)

    if not keyword:
        yield from bot.coro_send_message(
            event.conv,_("Unsubscribing all keywords"))
        _internal.keywords[event.user.id_.chat_id] = []
    elif keyword in _internal.keywords[event.user.id_.chat_id]:
        yield from bot.coro_send_message(
            event.conv,_("Unsubscribing from keyword '{}'").format(keyword))
        _internal.keywords[event.user.id_.chat_id].remove(keyword)
    else:
        yield from bot.coro_send_message(
            event.conv,_("Error: keyword not found"))

    # Save to file
    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "keywords"], _internal.keywords[event.user.id_.chat_id])
    bot.memory.save()


def testsubscribe(bot, event, *args):
    yield from _handle_keyword(bot, event, False, include_event_user=True)
