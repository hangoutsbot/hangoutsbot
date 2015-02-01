import asyncio,re

""" Cache to keep track of what keywords are being watched. Listed by user_id """
keywords = {}

def _initialise(command):
    # Pull the keywords from file

    bot.initialise_memory(event.user.id_.chat_id, "user_data")
    print("test")
    for userchatid in bot.memory.get_option("user_data"):
        print("test2")
        userkeywords = bot.memory.get_suboption("user_data", userchatid, "keywords")
        print("test3")
        if userkeywords:
            print("test4")
            keywords.append(userkeywords)

    command.register_handler(_handle_keyword)
    return ["subscribe", "unsubscribe"]

@asyncio.coroutine
def _handle_keyword(bot, event, command):
    yield from command.run(bot, event, *["mention_on_keyword"])

def subscribe(bot, event, *args):
    """allow users to subscribe to phrases"""

    keyword = ' '.join(args).strip()

    if(keyword == ''):
        bot.send_message_parsed(
            event.conv,"Usage: /bot subscribe <keyword>")
        return

    # Check for duplicates
    if keyword in keywords[event.user.id_.chat_id]:
        bot.send_message_parsed(
            event.conv,"Already subscribed to '{}'!".format(keyword))
        return

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

def mention_on_keyword(bot, event, *args):
    return
