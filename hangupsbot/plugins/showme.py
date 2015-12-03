"""
"showme" function to retrieve snapshots from security cameras or other URL's accessible to the hangupsbot server and
sent them to the user.

Config must specify aliases and urls which should include any nessisary auth.
"""

import time
import aiohttp, asyncio, io, logging
import plugins

logger = logging.getLogger(__name__)

def _initalize(bot):
    if bot.get_config_option("showme") is not None:
        plugins.register_user_command(["showme"])
    else:
        logger.error('SHOWME: config["showme"] dict required')

def showme(bot, event, *args):
    "Request snapshot and send message"
    sources = bot.get_config_option("showme")
    if not len(args):
        yield from bot.coro_send_message(event.conv, _("Show you what?"))
    elif args[0].lower() in ('sources','help'):
        html = "My sources are:<br />"
        for name in sources.keys():
            html += "* {}<br />".format(name)
        yield from bot.coro_send_message(event.conv, _(html))
    elif not args[0] in sources:
        yield from bot.coro_send_message(event.conv, _("I don't know a \"{}\", try help".format(args[0])))
    else:
        imgLink = sources[args[0]]
        logger.info("Getting {}".format(imgLink))
        r = yield from aiohttp.request("get", imgLink)
        raw = yield from r.read()
        contentType = r.headers['Content-Type']
        logger.info("\tContent-type: {}".format(contentType))
        ext = contentType.split('/')[1]
        image_data = io.BytesIO(raw)
        filename = "{}_{}.{}".format(args[0], int(time.time()), ext) # For the moment, we will just assume jpeg, really we should look inside the xheaders
        try:
            image_id = yield from bot._client.upload_image(image_data, filename=filename)
        except:
            yield from bot.coro_send_message(event.conv, _("I'm sorry, I couldn't upload a {} images".format(ext)))
        else:
            yield from bot.coro_send_message(event.conv.id_, None, image_id=image_id)
