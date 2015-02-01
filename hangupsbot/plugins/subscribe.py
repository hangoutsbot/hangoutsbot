import asyncio,re

""" Cache to keep track of what keywords are being watched. Listed by user_id """
keywords = {}

def _initialise(command):
    command.register_handler(_handle_keyword)

    # Pull the keywords from file
    for userchatid in bot.memory.get_option("user_data"):
        userkeywords = bot.memory.get_suboption("user_data", userchatid, "keywords")
        if userkeywords:
            keywords.append(userkeywords)

    return ["subscribe", "unsubscribe"]

@asyncio.coroutine
def _handle_keyword(bot, event, command):
    yield from command.run(bot, event, *["mention_on_keyword"])

def subscribe(bot, event, *args):
    return

def unsubscribe(bot, event, *args):
    return

def mention_on_keyword(bot, event, *args):
    return
