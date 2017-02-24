import re
import logging

import plugins

logger = logging.getLogger(__name__)


def _initialise():
    plugins.register_shared('image_validate_link', _image_validate_link)


def _image_validate_link(event_text, reject_googleusercontent=True):
    """
    validates and sanitises image link
    returns ( string original text/sanitised link,
              bool probably a link )
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
