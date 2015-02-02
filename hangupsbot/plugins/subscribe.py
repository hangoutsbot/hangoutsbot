import asyncio,re

""" Cache to keep track of what keywords are being watched. Listed by user_id """
keywords = {}

def _initialise(command):
    command.register_handler(_handle_keyword)
    return ["subscribe", "unsubscribe"]

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

@asyncio.coroutine
def _handle_keyword(bot, event, command):
    return

def subscribe(bot, event, *args):
    """allow users to subscribe to phrases"""
    _populate_keywords(bot, event)

    keyword = ' '.join(args).strip()

    if(keyword == ''):
        bot.send_message_parsed(
            event.conv,"Usage: /bot subscribe <keyword>")
        return

    # Check for duplicates, if none, append the keyword
    if keywords:
        if keyword in keywords[event.user.id_.chat_id]:
            bot.send_message_parsed(
                event.conv,"Already subscribed to '{}'!".format(keyword))
            return
        elif not keywords[event.user.id_.chat_id]:
            keywords[event.user.id_.chat_id] = [keyword]
        else:
            keywords[event.user.id_.chat_id].append(keyword)

    # Save to file
    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "keywords"], keywords[event.user.id_.chat_id])
    bot.memory.save()

    bot.send_message_parsed(
        event.conv,
        "Subscribing to '{}'".format(keyword))

def unsubscribe(bot, event, *args):
    return
