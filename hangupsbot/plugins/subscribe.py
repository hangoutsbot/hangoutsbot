import asyncio,re

""" Cache to keep track of what keywords are being watched. Listed by user_id """
keywords = {}

def _initialise(command):
    command.register_handler(_handle_keyword)
    return ["subscribe", "unsubscribe"]

def _populate_keywords(bot, event):
    # Pull the keywords from file
    if not keywords:
        bot.initialise_memory(event.user.id_.chat_id, "user_data")
        for userchatid in bot.memory.get_option("user_data"):
            userkeywords = bot.memory.get_suboption("user_data", userchatid, "keywords")
            if userkeywords:
                keywords.append(userkeywords)

@asyncio.coroutine
def _handle_keyword(bot, event, command):
    return

def subscribe(bot, event, *args):
    """allow users to subscribe to phrases"""
    print("Beginning subscribe")
    _populate_keywords(bot, event)
    print("Keywords populated")

    keyword = ' '.join(args).strip()

    if(keyword == ''):
        bot.send_message_parsed(
            event.conv,"Usage: /bot subscribe <keyword>")
        return

    print("Checking for dupes yo")
    # Check for duplicates
    if keywords[event.user.id_.chat_id]:
        print("Keywords check passed")
        if keyword in keywords[event.user.id_.chat_id]:
            print("Second keywords check passed")
            bot.send_message_parsed(
                event.conv,"Already subscribed to '{}'!".format(keyword))
            return

    print("Dupe check done")

    # Add to cache
    keywords[event.user.id_chat_id].append(keyword)

    # Save to file
    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "keywords"], keywords[event.user.id_.chat_id])
    bot.memory.save()

    bot.send_message_parsed(
        event.conv,
        "Subscribing to '{}'".format(keyword))

def unsubscribe(bot, event, *args):
    return
