import asyncio, logging, re

import plugins


logger = logging.getLogger(__name__)


class __internal_vars():
    def __init__(self):
        """ Cache to keep track of what keywords are being watched. Listed by user_id """
        self.keywords = {}

_internal = __internal_vars()


def _initialise():
    plugins.register_handler(_handle_keyword)
    plugins.register_user_command(["subscribe", "unsubscribe"])


def _handle_keyword(bot, event, command):
    """handle keyword"""

    _populate_keywords(bot, event)

    users_in_chat = event.conv.users

    """check if synced room, if so, append on the users"""
    sync_room_list = bot.get_config_suboption(event.conv_id, 'sync_rooms')
    if sync_room_list:
        if event.conv_id in sync_room_list:
            for syncedroom in sync_room_list:
                if event.conv_id not in syncedroom:
                    users_in_chat += bot.get_users_in_conversation(syncedroom)
            users_in_chat = list(set(users_in_chat)) # make unique

    for user in users_in_chat:
        try:
            if _internal.keywords[user.id_.chat_id] and not user.id_.chat_id in event.user.id_.chat_id:
                for phrase in _internal.keywords[user.id_.chat_id]:
                    regexphrase = "\\b" + phrase + "\\b"
                    if re.search(regexphrase, event.text, re.IGNORECASE):
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
    conv_1on1 = yield from bot.get_1to1(user.id_.chat_id)
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
