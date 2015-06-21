import asyncio,re,logging

from hangups.ui.utils import get_conv_name

class __internal_vars():
    def __init__(self):
        """ Cache to keep track of what keywords are being watched. Listed by user_id """
        self.keywords = {}

_internal = __internal_vars()

def _initialise(command):
    command.register_handler(_handle_keyword)
    return ["subscribe", "unsubscribe"]

@asyncio.coroutine
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
                        _send_notification(bot, event, phrase, user)
        except KeyError:
            # User probably hasn't subscribed to anything
            continue

def _populate_keywords(bot, event):
    # Pull the keywords from file if not already
    if not _internal.keywords:
        bot.initialise_memory(event.user.id_.chat_id, "user_data")
        for userchatid in bot.memory.get_option("user_data"):
            userkeywords = bot.memory.get_suboption("user_data", userchatid, "keywords")
            if userkeywords:
                _internal.keywords[userchatid] = userkeywords
            else:
                _internal.keywords[userchatid] = []

def _send_notification(bot, event, phrase, user):
    """Alert a user that a keyword that they subscribed to has been used"""

    conversation_name = get_conv_name(event.conv, truncate=True);
    logging.info(_("subscribe: keyword '{}' in '{}' ({})").format(phrase, conversation_name, event.conv.id_))

    """send alert with 1on1 conversation"""
    conv_1on1 = bot.get_1on1_conversation(user.id_.chat_id)
    if conv_1on1:
        try:
            user_has_dnd = bot.call_shared("dnd.user_check", user.id_.chat_id)
        except KeyError:
            user_has_dnd = False
        if not user_has_dnd: # shared dnd check
            bot.send_message_parsed(
                conv_1on1,
                _("<b>{}</b> mentioned '{}' in <i>{}</i>:<br />{}").format(
                    event.user.full_name,
                    phrase,
                    conversation_name,
                    event.text))
            logging.info(_("subscribe: {} ({}) alerted via 1on1 ({})").format(user.full_name, user.id_.chat_id, conv_1on1.id_))
        else:
            logging.info(_("subscribe: {} ({}) has dnd").format(user.full_name, user.id_.chat_id))
    else:
        logging.warning(_("subscribe: user {} ({}) could not be alerted via 1on1").format(user.full_name, user.id_.chat_id))

def subscribe(bot, event, *args):
    """allow users to subscribe to phrases, only one input at a time"""
    _populate_keywords(bot, event)

    keyword = ' '.join(args).strip().lower()

    conv_1on1 = bot.get_1on1_conversation(event.user.id_.chat_id)
    if not conv_1on1:
        bot.send_message_parsed(
            event.conv,
            _("Note: I am unable to ping you until you start a 1 on 1 conversation with me!"))

    if not keyword:
        bot.send_message_parsed(
            event.conv,_("Usage: /bot subscribe [keyword]"))
        if _internal.keywords[event.user.id_.chat_id]:
            bot.send_message_parsed(
                event.conv,
                _("Subscribed to: {}").format(', '.join(_internal.keywords[event.user.id_.chat_id])))
        return

    if event.user.id_.chat_id in _internal.keywords:
        if keyword in _internal.keywords[event.user.id_.chat_id]:
            # Duplicate!
            bot.send_message_parsed(
                event.conv,_("Already subscribed to '{}'!").format(keyword))
            return
        else:
            # Not a duplicate, proceeding
            if not _internal.keywords[event.user.id_.chat_id]:
                # First keyword!
                _internal.keywords[event.user.id_.chat_id] = [keyword]
                bot.send_message_parsed(
                    event.conv,
                    _("Note: You will not be able to trigger your own subscriptions. To test, please ask somebody else to test this for you."))
            else:
                # Not the first keyword!
                _internal.keywords[event.user.id_.chat_id].append(keyword)
    else:
        _internal.keywords[event.user.id_.chat_id] = [keyword]
        bot.send_message_parsed(
            event.conv,
            _("Note: You will not be able to trigger your own subscriptions. To test, please ask somebody else to test this for you."))


    # Save to file
    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "keywords"], _internal.keywords[event.user.id_.chat_id])
    bot.memory.save()

    bot.send_message_parsed(
        event.conv,
        _("Subscribed to: {}").format(', '.join(_internal.keywords[event.user.id_.chat_id])))

def unsubscribe(bot, event, *args):
    """Allow users to unsubscribe from phrases"""
    _populate_keywords(bot, event)

    keyword = ' '.join(args).strip().lower()

    if not keyword:
        bot.send_message_parsed(
            event.conv,_("Unsubscribing all keywords"))
        _internal.keywords[event.user.id_.chat_id] = []
    elif keyword in _internal.keywords[event.user.id_.chat_id]:
        bot.send_message_parsed(
            event.conv,_("Unsubscribing from keyword '{}'").format(keyword))
        _internal.keywords[event.user.id_.chat_id].remove(keyword)
    else:
        bot.send_message_parsed(
            event.conv,_("Error: keyword not found"))

    # Save to file
    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "keywords"], _internal.keywords[event.user.id_.chat_id])
    bot.memory.save()
