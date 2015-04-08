"""
example plugin which watches rename events
"""

import asyncio


def _initialise(Handlers, bot=None):
    Handlers.register_handler(_watch_rename, type="rename")
    return []


@asyncio.coroutine
def _watch_rename(bot, event, command):
    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return

    # Only print renames for now...
    if event.conv_event.new_name == '':
        print(_('EXAMPLE_PRINTRENAMES: {} cleared the conversation name').format(event.user.first_name))
    else:
        print(_('EXAMPLE_PRINTRENAMES: {} renamed the conversation to {}').format(event.user.first_name, event.conv_event.new_name))
