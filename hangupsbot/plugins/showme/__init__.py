"""
"showme" function to retrieve snapshots from security cameras or other URL's accessible to the hangupsbot server and
sent them to the user.

Config must specify aliases and urls which should include any nessisary auth.
"""
__LICENSE__ = """
The BSD License
Copyright (c) 2015, Daniel Casner
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
__author__ = "Daniel Casner <www.artificelab.com>"

import time
import aiohttp, asyncio, io, logging
import plugins

logger = logging.getLogger(__name__)

def _initalize(bot):
    if bot.get_config_option("showme") is not None:
        plugins.register_user_command(["showme"])
    else:
        logger.error('SHOWME: config["showme"] dict required')

def sendSource(bot, event, name, imgLink):
    logger.info("Getting {}".format(imgLink))
    r = yield from aiohttp.request("get", imgLink)
    raw = yield from r.read()
    contentType = r.headers['Content-Type']
    logger.info("\tContent-type: {}".format(contentType))
    ext = contentType.split('/')[1]
    image_data = io.BytesIO(raw)
    filename = "{}_{}.{}".format(name, int(time.time()), ext)
    try:
        image_id = yield from bot._client.upload_image(image_data, filename=filename)
    except:
        yield from bot.coro_send_message(event.conv, _("I'm sorry, I couldn't upload a {} image".format(ext)))
    else:
        yield from bot.coro_send_message(event.conv.id_, None, image_id=image_id)

def showme(bot, event, *args):
    """Retrieve images from showme sources by saying: "/bot showme SOURCE" or list sources by saying "/bot showme sources" or all sources by saying "/bot showme all" """
    sources = bot.get_config_option("showme")
    if not len(args):
        yield from bot.coro_send_message(event.conv, _("Show you what?"))
    elif args[0].lower() == 'sources':
        html = """My sources are:<br />"""
        for name in sources.keys():
            html += " * {}<br />".format(name)
        yield from bot.coro_send_message(event.conv, _(html))
    elif args[0].lower() == 'all':
        for name, source in sources.items():
            yield from sendSource(bot, event, name, source)
    elif not args[0] in sources:
        yield from bot.coro_send_message(event.conv, _("I don't know a \"{}\", try sources".format(args[0])))
    else:
        yield from sendSource(bot, event, args[0], sources[args[0]])
