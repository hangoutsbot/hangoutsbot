"""
Identify images, upload them to google plus, post in hangouts
"""

import aiohttp, asyncio, io, logging, os, re

from plugins._validate_image_links import imagelink

import plugins


logger = logging.getLogger(__name__)


def _initialise():
    plugins.register_handler(_watch_image_link, type="message")


@asyncio.coroutine
def _watch_image_link(bot, event, command):
    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return

    message, probable_image_link=imagelink(message)
		
        if probable_image_link:
            message = message.replace(".webm",".gif")
            message = message.replace(".gifv",".gif")

            logger.info("getting {}".format(message))

            filename = os.path.basename(message)
            r = yield from aiohttp.request('get', message)
            raw = yield from r.read()
            image_data = io.BytesIO(raw)

            image_id = yield from bot._client.upload_image(image_data, filename=filename)

        yield from bot.coro_send_message(event.conv.id_, None, image_id=image_id)