import asyncio, re, logging, json, random, aiohttp, io, os

import time

import plugins

import hangups

logger = logging.getLogger(__name__)

"""Image is set in config.json with "humor_hangoutcalls_image_url":"FULL PUBLIC LINK TO IMAGE""""

def _initialise(bot):
    plugins.register_handler(on_hangout_call, type="call")


def on_hangout_call(bot, event, command):
    if event.conv_event._event.hangout_event.event_type == hangups.schemas.ClientHangoutEventType.END_HANGOUT:
        lastcall = bot.conversation_memory_get(event.conv_id, "lastcall")
        if lastcall:
            lastcaller = lastcall["caller"]
            since = int(time.time() - lastcall["timestamp"])


            if since < 120:
                humantime = "{} seconds".format(since)
            elif since < 7200:
                humantime = "{} minutes".format(since // 60)
            elif since < 172800:
                humantime = "{} hours".format(since // 3600)
            else:
                humantime = "{} days".format(since // 86400)

            if bot.conversations.catalog[event.conv_id]["type"] == "ONE_TO_ONE":
                """subsequent calls for a ONE_TO_ONE"""
                yield from bot.coro_send_message(event.conv_id,
                    _("<b>It's been {} since the last call. Lonely? I can't reply you as I don't have speech synthesis (or speech recognition either!)</b>").format(humantime))
            else:
                """subsequent calls for a GROUP"""
                if not bot.get_config_suboption(event.conv_id, 'humor_hangoutcalls_image_url'):
                    """image url not set just send text"""
                    logger.debug("humor_hangoutcalls_image_url not set.")
                    yield from bot.coro_send_message(event.conv_id,
                        _(" <b>It's been {} since the last call. The previous caller was <i>{}</i>.</b>").format(humantime, lastcaller))
                else:
                    """image url set send text then image if url appears to be an image"""
                    yield from bot.coro_send_message(event.conv_id,
                        _(" <b>It's been {} since the last call. The previous caller was <i>{}</i>.</b>").format(humantime, lastcaller))
                    link_image = bot.get_config_suboption(event.conv_id, 'humor_hangoutcalls_image_url')
                    if " " in link_image:
                        """immediately reject anything with spaces, must be a link"""
                        logger.info("URL appears to be bad, not attempting image".format(link_image))
                        return

                    probable_image_link = False
                    event_text_lower = link_image.lower()

                    if re.match("^(https?://)?([a-z0-9.]*?\.)?imgur.com/", event_text_lower, re.IGNORECASE):
                        """imgur links can be supplied with/without protocol and extension"""
                        probable_image_link = True

                    elif event_text_lower.startswith(("http://", "https://")) and event_text_lower.endswith((".png", ".gif", ".gifv", ".jpg", ".jpeg")):
                        """other image links must have protocol and end with valid extension"""
                        probable_image_link = True

                    if probable_image_link:
                        if "imgur.com" in link_image:
                            """special imgur link handling"""
                            if not link_image.endswith((".jpg", ".gif", "gifv", "webm", "png")):
                                link_image = link_image + ".gif"
                            link_image = "https://i.imgur.com/" + os.path.basename(link_image)

                        link_image = link_image.replace(".webm",".gif")
                        link_image = link_image.replace(".gifv",".gif")

                        logger.info("getting {}".format(link_image))

                        filename = os.path.basename(link_image)
                        r = yield from aiohttp.request('get', link_image)
                        raw = yield from r.read()
                        image_data = io.BytesIO(raw)
                        image_id = yield from bot._client.upload_image(image_data, filename=filename)
                        yield from bot.coro_send_message(event.conv.id_, None, image_id=image_id)

        else:
            """first ever call for any conversation"""
            yield from bot.coro_send_message(event.conv_id,
                _("<b>No prizes for that call</b>"))

        bot.conversation_memory_set(event.conv_id, "lastcall", { "caller": event.user.full_name, "timestamp": time.time() })
