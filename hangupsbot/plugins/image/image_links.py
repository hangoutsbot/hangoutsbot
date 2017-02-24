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
        """
        INCLUDE THE [image] PLUGIN IN YOUR CONFIGURATION
        IN THE FUTURE, THIS WILL FAIL GRACEFULLY AND NOTHING WILL HAPPEN
        DEVELOPERS+BOTMINS: CONSIDER YOURSELF WARNED
        """
        # return
        try:
            logger.warning('image plugin not loaded - attempting to directly import plugin')
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


def _fallback_image_validate_link(event_text, reject_googleusercontent=True):
    """
    FALLBACK FOR BACKWARD-COMPATIBILITY
    INCLUDE [image] PLUGIN IN YOUR CONFIGURATION
    DO NOT RELY ON THIS AS A PRINCIPAL FUNCTION
    DO NOT MODIFY THIS CODE
    MAY BE REMOVED ON THE WHIM OF THE FRAMEWORK DEVELOPERS
    """

    if " " in event_text:
        """immediately reject anything with non url-encoded spaces (%20)"""
        return event_text, False

    probable_image_link = False

    event_text_lower = event_text.lower()

    if re.match("^(https?://)?([a-z0-9.]*?\.)?imgur.com/", event_text_lower, re.IGNORECASE):
        """imgur links can be supplied with/without protocol and extension"""
        probable_image_link = True

    elif event_text_lower.startswith(("http://", "https://")) and event_text_lower.endswith((".png", ".gif", ".gifv", ".jpg", ".jpeg")):
        """other image links must have protocol and end with valid extension"""
        probable_image_link = True

    if probable_image_link and reject_googleusercontent and ".googleusercontent." in event_text_lower:
        """reject links posted by google to prevent endless attachment loop"""
        logger.debug("rejected link {} with googleusercontent".format(event_text))
        return event_text, False

    if probable_image_link:

        """special handler for imgur links"""
        if "imgur.com" in event_text:
            if not event_text.endswith((".jpg", ".gif", "gifv", "webm", "png")):
                event_text = event_text + ".gif"
            event_text = "https://i.imgur.com/" + os.path.basename(event_text)

            """XXX: animations - this code looks fragile"""
            event_text = event_text.replace(".webm",".gif")
            event_text = event_text.replace(".gifv",".gif")

        logger.info('{} seems to be a valid image link'.format(event_text))

    return event_text, probable_image_link
