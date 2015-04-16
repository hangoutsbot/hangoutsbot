import asyncio
import aiohttp
import re
import logging
import os
import io

from hangups.ui.utils import get_conv_name

def _initialise(command):
    command.register_handler(_handle_autoreply)
    return []

@asyncio.coroutine
def _handle_autoreply(bot, event, command):
    """Handle autoreplies to champagne in messages"""
    
    if champagne_in_text(event.text): 
        link_image = "http://blessingtonlakesgolfclub.com/wp-content/uploads/2013/10/Champagne.jpg"
        filename = os.path.basename(link_image)
        r = yield from aiohttp.request('get', link_image)
        raw = yield from r.read()
        image_data = io.BytesIO(raw)
        image_id = yield from bot._client.upload_image(image_data, filename=filename)
        bot.send_message_segments(event.conv.id_, None, image_id=image_id)

def champagne_in_text(text):
    """Return True if word is in text"""

    #TODO: This is identical to regex in line 33 of subscribe.py!
    regexword = "\\b" + "Champagne*(?=!)" + "\\b"

    return True if re.search(regexword, text, re.IGNORECASE) else False
