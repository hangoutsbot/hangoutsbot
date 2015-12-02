"""
example plugin which watches rename events
"""

import asyncio, logging


logger = logging.getLogger(__name__)


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
        logger.info('{} cleared the conversation name'.format(event.user.first_name))
    else:
        logger.info('{} renamed the conversation to {}'.format(event.user.first_name, event.conv_event.new_name))
