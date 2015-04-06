"""
Identify images, upload them to google plus, post in hangouts
"""

import asyncio
import aiohttp
import asyncio
import os
import io

def _initialise(Handlers, bot=None):
    Handlers.register_handler(_watch_image_link, type="message")
    return []


@asyncio.coroutine
def _watch_image_link(bot, event, command):
    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return

    # Detecting a photo
    if (".jpg" in event.text or "imgur.com" in event.text or ".png" in event.text or ".gif" in event.text or ".gifv" in event.text) and "googleusercontent" not in event.text:

        if "imgur.com" in event.text:
            link_image = event.text
            if not link_image.endswith((".jpg", ".gif", "gifv", "png")):
                link_image = link_image + ".gif"
            link_image = "https://i.imgur.com/" + os.path.basename(link_image)
 
        link_image = link_image.replace(".gifv",".gif")

        print("image(): getting {}".format(link_image))

        filename = os.path.basename(link_image)
        r = yield from aiohttp.request('get', link_image)
        raw = yield from r.read()
        image_data = io.BytesIO(raw)

        image_id = yield from bot._client.upload_image(image_data, filename=filename)

        yield from bot._client.sendchatmessage(event.conv.id_, None, image_id=image_id)