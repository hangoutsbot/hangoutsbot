import asyncio
#for image
import aiohttp
import logging
import os
import io
#for test presence in text
import re
#for timer
import time

from hangups.ui.utils import get_conv_name

keyword = "champagne"
cooldown = 4*3600
times = 4

def _initialise(command, bot=None):
    _create_champagne_in_memory(bot)
    command.register_handler(_handle_autoreply)
    return []

def _create_champagne_in_memory(bot):
    cd = 4*3600
    max = 4
    # migrate DND list to memory.json
    champagne = {}
    bot.memory.set_by_path([keyword], champagne)
    bot.memory.save()

    # migrate memory.json DND to structure with more metadata
    if bot.memory.exists(["donotdisturb"]):
        donotdisturb = bot.memory.get("donotdisturb")
        if(isinstance(donotdisturb, list)):
            # legacy structure, convert to dict
            dnd_dict = {}
            for user_id in donotdisturb:
                dnd_dict[user_id] = {
                    "created": time.time(),
                    "expiry": 86400
                }
            bot.memory.set_by_path(["donotdisturb"], dnd_dict)
            bot.memory.save()

@asyncio.coroutine
def _handle_autoreply(bot, event, command):
    """Handle autoreplies to champagne in messages"""
    if champagne_in_text(event.text):
        if is_burn(bot, event):
            bot.send_message(event.conv, "L'abus d'alcool est mauvais pour la santé.")
        else:
            # TODO: Use local image
            link_image = "http://deberdt.fr/Ingress/Champagne.jpg"
            filename = os.path.basename(link_image)
            r = yield from aiohttp.request('get', link_image)
            raw = yield from r.read()
            image_data = io.BytesIO(raw)
            image_id = yield from bot._client.upload_image(image_data, filename=filename)
            bot.send_message_segments(event.conv.id_, None, image_id=image_id)

def champagne_in_text(text):
    """Return True if Champagne*! is in text"""
    regexword = "\\b" + "Champagne+(?=!)" + "\\b"
    return True if re.search(regexword, text, re.IGNORECASE) else False

def is_burn(bot, event):
    """"Check number of times this autoreply was used and limit it"""
    champagne = bot.memory.get(keyword)
    conv_id = event.conv.id_
    if conv_id in champagne:
        hacks = champagne[conv_id]["hack"]
        if hacks >= times:
            if champagne[conv_id]["timer"] + cooldown > time.time():
                return True
            else:
                heat_sink(bot, conv_id)
                hack(bot, conv_id)
                return False
        else:
            if hack == 0:
                heat_sink(bot, conv_id)
                hack(bot, conv_id)
                return False
            else:
                hack(bot, conv_id)
                return False
    else:
        heat_sink(bot, conv_id)
        hack(bot, conv_id)
        return False
    return True

def heat_sink(bot, conv_id):
    hack_status = {
        "timer": time.time(),
        "hack": 0
    }
    champagne = bot.memory.get(keyword)
    champagne[conv_id] = hack_status
    bot.memory.set_by_path([keyword], champagne)
    bot.memory.save()

def hack(bot, conv_id):
    champagne = bot.memory.get(keyword)
    champagne[conv_id]["hack"] = champagne[conv_id]["hack"] + 1
    bot.memory.set_by_path([keyword], champagne)
    bot.memory.save()