import aiohttp, asyncio, logging, os, io

import hangups

import plugins


logger = logging.getLogger(__name__)


def _initialise():
    plugins.register_handler(_handle_forwarding, type="message")


@asyncio.coroutine
def _handle_forwarding(bot, event, command):
    """Handle message forwarding"""
    # Test if message forwarding is enabled
    if not bot.get_config_suboption(event.conv_id, 'forwarding_enabled'):
        return

    forward_to_list = bot.get_config_suboption(event.conv_id, 'forward_to')
    if forward_to_list:
        logger.debug("{}".format(forward_to_list))

        for _conv_id in forward_to_list:
            html_identity = "<b><a href='https://plus.google.com/u/0/{}/about'>{}</a></b><b>:</b> ".format(event.user_id.chat_id, event.user.full_name)

            html_message = event.text

            if not event.conv_event.attachments:
                yield from bot.coro_send_message( _conv_id,
                                                  html_identity + html_message )

            for link in event.conv_event.attachments:

                filename = os.path.basename(link)
                r = yield from aiohttp.request('get', link)
                raw = yield from r.read()
                image_data = io.BytesIO(raw)
                image_id = None

                try:
                    image_id = yield from bot._client.upload_image(image_data, filename=filename)
                    if not html_message:
                        html_message = "(sent an image)"
                    yield from bot.coro_send_message( _conv_id,
                                                      html_identity + html_message,
                                                      image_id=image_id )

                except AttributeError:
                    yield from bot.coro_send_message( _conv_id,
                                                      html_identity + html_message + " " + link )
