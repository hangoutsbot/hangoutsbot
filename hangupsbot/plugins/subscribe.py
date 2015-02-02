import asyncio,re

""" Cache to keep track of what keywords are being watched. Listed by user_id """
keywords = {}

def _initialise(command):
    command.register_handler(_handle_keyword)
    return ["subscribe", "unsubscribe"]

@asyncio.coroutine
def _handle_keyword(bot, event, command):
    """handle keyword"""
    print("Handling keyword")

    _populate_keywords(bot, event)

    users_in_chat = event.conv.users

    for user in users_in_chat:
        if keywords[user.id_.chat_id]:
            for phrase in keywords[user.id_.chat_id]:
                if phrase in event.text:
                    print("{} found!".format(phrase))
                else:
                    print("{} not found".format(phrase))

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

def subscribe(bot, event, *args):
    """allow users to subscribe to phrases"""
    _populate_keywords(bot, event)

    keyword = ' '.join(args).strip()

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
