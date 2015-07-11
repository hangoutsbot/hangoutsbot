import os, io

import aiohttp
import asyncio
import hangups

def _initialise(Handlers, bot=None):
    Handlers.register_handler(_handle_forwarding, type="message")
    return []

@asyncio.coroutine
def _handle_forwarding(bot, event, command):
    """Handle message forwarding"""
    # Test if message forwarding is enabled
    if not bot.get_config_suboption(event.conv_id, 'forwarding_enabled'):
        return

    forward_to_list = bot.get_config_suboption(event.conv_id, 'forward_to')
    if forward_to_list:
        print(_("FORWARDING: {}").format(forward_to_list))
        for _conv_id in forward_to_list:
            html = "<b><a href='https://plus.google.com/u/0/{}/about'>{}</a></b>: ".format(event.user_id.chat_id, event.user.full_name)
            for segment in event.conv_event.segments:
                html += segment.text

            # Append attachments (G+ photos) to forwarded message
            if not event.conv_event.attachments:
                bot.send_html_to_conversation(_conv_id, html)

            for link in event.conv_event.attachments:
                # Attempt to upload the photo first
                filename = os.path.basename(link)
                r = yield from aiohttp.request('get', link)
                raw = yield from r.read()
                image_data = io.BytesIO(raw)
                image_id = None

                try:
                    image_id = yield from bot._client.upload_image(image_data, filename=filename)
                    html += "<br /><i>Incoming image...</i><br />"
                except AttributeError:
                    html += link + "<br />"

                bot.send_html_to_conversation(_conv_id, html)
                if image_id:
                    bot.send_message_segments(_conv_id, None, image_id=image_id)
