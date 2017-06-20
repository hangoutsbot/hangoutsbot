import re
import logging

import aiohttp
import asyncio
import io
import os


import plugins

logger = logging.getLogger(__name__)

_externals = { "bot": None }


def _initialise(bot):
    _externals["bot"] = bot
    plugins.register_shared('image_validate_link', image_validate_link)
    plugins.register_shared('image_upload_single', image_upload_single)
    plugins.register_shared('image_upload_raw', image_upload_raw)
    plugins.register_shared('image_validate_and_upload_single', image_validate_and_upload_single)


def image_validate_link(image_uri, reject_googleusercontent=True):
    """
    validate and possibly mangle supplied image link
    returns False, if not an image link
            <string image uri>
    """

    if " " in image_uri:
        """immediately reject anything with non url-encoded spaces (%20)"""
        return False

    probable_image_link = False

    image_uri_lower = image_uri.lower()

    if re.match("^(https?://)?([a-z0-9.]*?\.)?imgur.com/", image_uri_lower, re.IGNORECASE):
        """imgur links can be supplied with/without protocol and extension"""
        probable_image_link = True

    elif re.match(r'^https?://gfycat.com', image_uri_lower):
        """imgur links can be supplied with/without protocol and extension"""
        probable_image_link = True

    elif image_uri_lower.startswith(("http://", "https://", "//")) and image_uri_lower.endswith((".png", ".gif", ".gifv", ".jpg", ".jpeg")):
        """other image links must have protocol and end with valid extension"""
        probable_image_link = True

    if probable_image_link and reject_googleusercontent and ".googleusercontent." in image_uri_lower:
        """reject links posted by google to prevent endless attachment loop"""
        logger.debug("rejected link {} with googleusercontent".format(image_uri))
        return False

    if probable_image_link:

        if "imgur.com" in image_uri:
            if not image_uri.endswith((".jpg", ".gif", "gifv", "webm", "png")):
                image_uri = image_uri + ".gif"
            image_uri = "https://i.imgur.com/" + os.path.basename(image_uri)

            """imgur wraps animations in player, force the actual image resource"""
            image_uri = image_uri.replace(".webm",".gif")
            image_uri = image_uri.replace(".gifv",".gif")

        elif re.match(r'^https?://gfycat.com', image_uri):
            image_uri = re.sub(r'^https?://gfycat.com/', 'https://thumbs.gfycat.com/', image_uri) + '-size_restricted.gif'

        logger.info('{} seems to be a valid image link'.format(image_uri))

        return image_uri

    return False


@asyncio.coroutine
def image_upload_single(image_uri):
    logger.debug("getting {}".format(image_uri))
    filename = os.path.basename(image_uri)
    try:
        r = yield from aiohttp.request('get', image_uri)
        content_type = r.headers['Content-Type']
        if not content_type.startswith('image/') and not content_type == "application/octet-stream":
            logger.warning("request did not return image/image-like data, content-type={}, headers={}".format(content_type, r.headers))
            return False
        raw = yield from r.read()
    except (aiohttp.errors.ClientError) as exc:
        logger.warning("failed to get {} - {}".format(filename, exc))
        return False
    image_data = io.BytesIO(raw)
    image_id = yield from image_upload_raw(image_data, filename=filename)
    return image_id


@asyncio.coroutine
def image_upload_raw(image_data, filename):
    image_id = False
    try:
        image_id = yield from _externals["bot"]._client.upload_image(image_data, filename=filename)
    except KeyError as exc:
        logger.warning("_client.upload_image failed: {}".format(exc))
    return image_id


@asyncio.coroutine
def image_validate_and_upload_single(text, reject_googleusercontent=True):
    image_id = False
    image_link = image_validate_link(text, reject_googleusercontent=reject_googleusercontent)
    if image_link:
        image_id = yield from image_upload_single(image_link)
    return image_id
