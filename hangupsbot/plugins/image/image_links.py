"""
Identify images, upload them to google plus, post in hangouts
"""

import aiohttp, asyncio, io, logging, os, re

import plugins


logger = logging.getLogger(__name__)


def _initialise():
    plugins.register_handler(_watch_image_link, type="message")


@asyncio.coroutine
def _watch_image_link(bot, event, command):
    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return

    message = event.text

    try:
        message, probable_image_link = bot.call_shared('image_validate_link', message)
    except KeyError:
        logger.warning('image plugin not loaded - attempting to directly import plugin')
        """
        in the future, just fail gracefully with no fallbacks
        DEVELOPERS: CONSIDER YOURSELF WARNED
        """
        # return
        try:
            from plugins.image import _image_validate_link as image_validate_link
            message, probable_image_link = image_validate_link(message)
        except ImportError:
            logger.warning('image module is not available - using fallback')
            message, probable_image_link = _fallback_image_validate_link(message)

    if probable_image_link:
        logger.info("getting {}".format(message))

        filename = os.path.basename(message)
        r = yield from aiohttp.request('get', message)
        raw = yield from r.read()
        image_data = io.BytesIO(raw)
        image_id = yield from bot._client.upload_image(image_data, filename=filename)

        yield from bot.coro_send_message(event.conv.id_, None, image_id=image_id)


def _fallback_image_validate_link(message):
    """
    FALLBACK FOR BACKWARD-COMPATIBILITY
    DO NOT RELY ON THIS AS A PRINCIPAL FUNCTION
    MAY BE REMOVED ON THE WHIM OF THE FRAMEWORK DEVELOPERS
    """

    probable_image_link = False

    if " " in message:
        """ignore anything with spaces"""
        probable_image_link = False

    message_lower = message.lower()
    logger.info("link? {}".format(message_lower))

    if re.match("^(https?://)?([a-z0-9.]*?\.)?imgur.com/", message_lower, re.IGNORECASE):
        """imgur links can be supplied with/without protocol and extension"""
        probable_image_link = True

    else:
        if message_lower.startswith(("http://", "https://")) and message_lower.endswith((".png", ".gif", ".gifv", ".jpg", ".jpeg")):
            """other image links must have protocol and end with valid extension"""
            probable_image_link = True
        else:
            probable_image_link = False

    if probable_image_link:

        """imgur links"""
        if "imgur.com" in message:
            if not message.endswith((".jpg", ".gif", "gifv", "webm", "png")):
                message = message + ".gif"
            message = "https://i.imgur.com/" + os.path.basename(message)

        """XXX: animations"""
        message = message.replace(".webm",".gif")
        message = message.replace(".gifv",".gif")

    return message, probable_image_link
