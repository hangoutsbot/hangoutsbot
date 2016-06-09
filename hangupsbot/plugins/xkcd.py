import plugins

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
		match = re.search(regexp, event.text)
		if not match:
			continue
		
		num = match.group(1)
		request = yield from aiohttp.request('get', 'https://xkcd.com/%s/info.0.json' % num)
		raw = yield from request.read()
		info = json.loads(raw)
		
		filename = os.path.basename(info["img"])
		request = yield from aiohttp.request('get', info["img"])
		raw = yield from request.read()
		image_data = io.BytesIO(raw)
		image_id = yield from bot._client.upload_image(image_data, filename=filename)
		
		context = {
			"parser": False,
		}
		
		msg1 = 'xkcd #%s: %s' % (num, info["title"])
		msg2 = '%s\n- https://xkcd.com/%s' % (info["alt"], num)
		if "link" in info and info["link"]:
			msg2 += "\n* see also %s" % info["link"]
		
		yield from bot.coro_send_message(event.conv.id_, msg1, context)
		yield from bot.coro_send_message(event.conv.id_, msg2, context, image_id=image_id) # image appears above text, so order is [msg1, image, msg2]
		
		return # only one match per message
