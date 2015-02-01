import asyncio,re

def _initialise(command):
    command.register_handler(_handle_keyword)
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
