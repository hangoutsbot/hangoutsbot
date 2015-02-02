import asyncio,re,logging

from hangups.ui.utils import get_conv_name

""" Cache to keep track of what keywords are being watched. Listed by user_id """
keywords = {}

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
            if keywords[user.id_.chat_id] and not user.id_.chat_id in event.user.id_.chat_id:
                for phrase in keywords[user.id_.chat_id]:
                    if phrase.lower() in event.text.lower():
                        _send_notification(bot, event, phrase, user)
        except KeyError:
            # User probably hasn't subscribed to anything
            continue

def _populate_keywords(bot, event):
    # Pull the keywords from file if not already
    if not keywords:
        bot.initialise_memory(event.user.id_.chat_id, "user_data")
        for userchatid in bot.memory.get_option("user_data"):
            userkeywords = bot.memory.get_suboption("user_data", userchatid, "keywords")
            if userkeywords:
                keywords[userchatid] = userkeywords
            else:
                keywords[userchatid] = []

def _send_notification(bot, event, phrase, user):
    """Alert a user that a keyword that he subscribed to has been used"""

    conversation_name = get_conv_name(event.conv, truncate=True);
    logging.info("Keyword found: '{}' in '{}' ({})".format(phrase, conversation_name, event.conv.id_))

    """pushbullet integration"""
    pushbullet_integration = bot.get_config_suboption(event.conv.id_, 'pushbullet')
    if pushbullet_integration is not None:
        if user.id_.chat_id in pushbullet_integration.keys():
            pushbullet_config = pushbullet_integration[user.id_.chat_id]
            if pushbullet_config["api"] is not None:
                pb = PushBullet(pushbullet_config["api"])
                success, push = pb.push_note(
                    "{} mentioned '{}' in {}".format(
                        event.user.full_name,
                        phrase,
                        conversation_name,
                        event.text))
                if success:
                    logging.info("{} ({}) alerted via pushbullet".format(user.full_name, user.id_.chat_id))
                    return
                else:
                    logging.warning("pushbullet alert failed for {} ({})".format(user.full_name, user.id_.chat_id))

    """send alert with 1on1 conversation"""
    conv_1on1 = bot.get_1on1_conversation(user.id_.chat_id)
    if conv_1on1:
        bot.send_message_parsed(
            conv_1on1,
            "<b>{}</b> mentioned '{}' in <i>{}</i>:<br />{}".format(
                event.user.full_name,
                phrase,
                conversation_name,
                event.text))
        logging.info("{} ({}) alerted via 1on1 ({})".format(user.full_name, user.id_.chat_id, conv_1on1.id_))
    else:
        logging.warning("user {} ({}) could not be alerted via 1on1".format(user.full_name, user.id_.chat_id))

def subscribe(bot, event, *args):
    """allow users to subscribe to phrases"""
    _populate_keywords(bot, event)

    keyword = ' '.join(args).strip().lower()

    if(keyword == ''):
        bot.send_message_parsed(
            event.conv,"Usage: /bot subscribe <keyword>")
        return

    if keywords:
        if keyword in keywords[event.user.id_.chat_id]:
            # Duplicate!
            bot.send_message_parsed(
                event.conv,"Already subscribed to '{}'!".format(keyword))
            return
        elif not keywords[event.user.id_.chat_id]:
            # First keyword!
            keywords[event.user.id_.chat_id] = [keyword]
            bot.send_message_parsed(
                event.conv,
                "Note: You will not be able to trigger your own subscriptions. To test, please ask somebody else to test this for you.")
        else:
            # Not the first keyword
            keywords[event.user.id_.chat_id].append(keyword)

    # Save to file
    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "keywords"], keywords[event.user.id_.chat_id])
    bot.memory.save()

    bot.send_message_parsed(
        event.conv,
        "Subscribed to: {}".format(', '.join(keywords[event.user.id_.chat_id])))

def unsubscribe(bot, event, *args):
    """Allow users to unsubscribe from phrases"""
    _populate_keywords(bot, event)

    keyword = ' '.join(args).strip()

    if(keyword == ''):
        bot.send_message_parsed(
            event.conv,"Unsubscribing all keywords")
        keywords[event.user.id_.chat_id] = []

    if keyword in keywords[event.user.id_.chat_id]:
        bot.send_message_parsed(
            event.conv,"Unsubscribing from keyword '{}'!".format(keyword))
        keywords[event.user.id_.chat_id].remove(keyword)

    # Save to file
    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "keywords"], keywords[event.user.id_.chat_id])
    bot.memory.save()
