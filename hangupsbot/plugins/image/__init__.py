import re
import logging

import plugins

logger = logging.getLogger(__name__)


def _initialise():
    plugins.register_shared('image_validate_link', _image_validate_link)


def _image_validate_link(message):
    """ validates a image link """

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
