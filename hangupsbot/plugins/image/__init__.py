import aiohttp
import asyncio
import io
import logging
import os
import re
import sys

from asyncio.subprocess import PIPE

import plugins


logger = logging.getLogger(__name__)


_externals = { "bot": None,
               "ClientSession": aiohttp.ClientSession() }


try:
    aiohttp_clienterror = aiohttp.ClientError
except AttributeError:
    aiohttp_clienterror = aiohttp.errors.ClientError
    logger.warning("[DEPRECATED]: aiohttp < 2.0")


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
    filename = os.path.basename(image_uri)
    logger.info("fetching {}".format(filename))
    try:
        r = yield from _externals["ClientSession"].get(image_uri)
        content_type = r.headers['Content-Type']

        image_handling = False # must == True if valid image, can contain additonal directives

        """image handling logic for specific image types - if necessary, guess by extension"""

        if content_type.startswith('image/'):
            if content_type == "image/webp":
                image_handling = "image_convert_to_png"
            else:
                image_handling = "standard"

        elif content_type == "application/octet-stream":
            ext = filename.split(".")[-1].lower() # guess the type from the extension

            if ext in ("jpg", "jpeg", "jpe", "jif", "jfif", "gif", "png"):
                image_handling = "standard"
            elif ext in ("webp"):
                image_handling = "image_convert_to_png"

        if image_handling:
            logger.debug("reading {}".format(image_uri))
            raw = yield from r.read()
            logger.debug("finished {}".format(image_uri))
            if image_handling is not "standard":
                try:
                    results = yield from getattr(sys.modules[__name__], image_handling)(raw)
                    if results:
                        # allow custom handlers to fail gracefully
                        raw = results
                except Exception as e:
                    logger.exception("custom image handler failed: {}".format(image_handling))
        else:
            logger.warning("not image/image-like, filename={}, headers={}".format(filename, r.headers))
            return False

    except (aiohttp_clienterror) as exc:
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


@asyncio.coroutine
def image_convert_to_png(image):
    path_imagemagick = _externals["bot"].get_config_option("image.imagemagick") or "/usr/bin/convert"
    cmd = (path_imagemagick, "-", "png:-")

    try:
        proc = yield from asyncio.create_subprocess_exec(
            *cmd,
            stdin = PIPE,
            stdout = PIPE,
            stderr = PIPE )

        (stdout_data, stderr_data) = yield from proc.communicate(input=image)

        return stdout_data

    except FileNotFoundError:
        logger.error("imagemagick not found at path {}".format(path_imagemagick))
        return False
