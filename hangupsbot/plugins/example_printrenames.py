import asyncio

from random import randint

def _initialise(command):
    command.register_handler(_watch_rename, type="rename")


@asyncio.coroutine
def _watch_rename(bot, event, command):
    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return

    # Only print renames for now...
    if event.conv_event.new_name == '':
        print('{} cleared the conversation name'.format(event.user.first_name))
    else:
        print('{} renamed the conversation to {}'.format(event.user.first_name, event.conv_event.new_name))