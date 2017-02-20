import asyncio, re, logging, json, random, aiohttp, io, os

logger = logging.getLogger(__name__)
  
def imagelink(message):
    """ validates a image link """	
    
    """starts as false"""
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
        if "imgur.com" in message:
            """special imgur link handling"""
            if not message.endswith((".jpg", ".gif", "gifv", "webm", "png")):
                message = message + ".gif"
            message = "https://i.imgur.com/" + os.path.basename(message)
 
    return message, probable_image_link