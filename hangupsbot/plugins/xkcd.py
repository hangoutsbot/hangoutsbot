# vim: set ts=4 expandtab sw=4

import plugins
from hangups import ChatMessageSegment

import aiohttp
import asyncio
import io
import json
import os.path
import re

def _initialise():
    plugins.register_handler(_watch_xkcd_link, type="message")

regexps = (
    "https?://(?:www\.)?(?:explain)?xkcd.com/([0-9]+)(?:/|\s|$)",
    "https?://(?:www\.)?explainxkcd.com/wiki/index\.php(?:/|\?title=)([0-9]+)(?:[^0-9]|$)",
    "(?:\s|^)xkcd\s+(?:#\s*)?([0-9]+)(?:\s|$)",
)

@asyncio.coroutine
def _watch_xkcd_link(bot, event, command):
    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return
    
    for regexp in regexps:
        match = re.search(regexp, event.text, flags=re.IGNORECASE)
        if not match:
            continue
        
        num = match.group(1)
        request = yield from aiohttp.request('get', 'https://xkcd.com/%s/info.0.json' % num)
        raw = yield from request.read()
        info = json.loads(raw.decode())
        
        filename = os.path.basename(info["img"])
        request = yield from aiohttp.request('get', info["img"])
        raw = yield from request.read()
        image_data = io.BytesIO(raw)
        image_id = yield from bot._client.upload_image(image_data, filename=filename)
        
        context = {
            "parser": False,
        }
        
        msg1 = [
            ChatMessageSegment("xkcd #%s: " % num),
            ChatMessageSegment(info["title"], is_bold=True),
        ]
        msg2 = [
            ChatMessageSegment(info["alt"]),
            *ChatMessageSegment.from_str('<br/>- <i><a href="https://xkcd.com/%s">CC-BY-SA by xkcd</a></i>' % num)
        ]
        if "link" in info and info["link"]:
            msg2.extend(ChatMessageSegment.from_str("<br/>* see also %s" % info["link"]))
        
        yield from bot.coro_send_message(event.conv.id_, msg1, context)
        yield from bot.coro_send_message(event.conv.id_, msg2, context, image_id=image_id) # image appears above text, so order is [msg1, image, msg2]
        
        return # only one match per message
