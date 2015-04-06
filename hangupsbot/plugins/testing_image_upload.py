"""
Identify images, upload them to google plus, post in hangouts
"""

import asyncio, aiohttp, asyncio, os, io

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

        if("imgur.com" in event.text and ".jpg" not in event.text and ".gif" not in event.text and ".gifv" not in event.text and ".png" not in event.text):
            event.text = event.text + ".gif"
            if "/gallery/" in event.text:
                event.text = event.text.replace("/gallery/", "/")

        downloadURL = event.text.replace(".gifv",".gif")

        print("image(): getting {}".format(downloadURL))

        filename = os.path.basename(downloadURL)
        r = yield from aiohttp.request('get', downloadURL)
        raw = yield from r.read()
        image_data = io.BytesIO(raw)

        image_id = yield from bot._client.upload_image(image_data, filename=filename)

        yield from bot._client.sendchatmessage(event.conv.id_, None, image_id=image_id)