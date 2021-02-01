import aiohttp, asyncio, logging, os, io, requests
import hangups
import plugins


logger = logging.getLogger(__name__)


def _initialise():
    plugins.register_handler(_handle_forwarding, type="allmessages")


@asyncio.coroutine
def _handle_forwarding(bot, event):
    """Handle message forwarding"""

    # Test if message forwarding is enabled
    if not bot.get_config_suboption(event.conv_id, 'discord_forward'):
        return

    if event.user.is_self:
        return

    discord_webhook = bot.get_config_suboption(event.conv_id, 'discord_webhook')
    if discord_webhook:
        username = event.user.full_name
        logging.info("event.text: ".format(event.text))
        logging.info("event.conv_event.segments: {}".format(event.conv_event.segments))
        try:
            avatar = "http:" + bot._user_list.get_user(event.user_id).photo_url
        except Exception as e:
            avatar = ""

        try:
            assert not isinstance(discord_webhook, str)
            discord_url = discord_webhook.pop()
            discord_webhook.insert(0, discord_url)
            bot.config.set_by_path(["conversations", event.conv_id, 'discord_webhook'], discord_webhook)
        except AssertionError:
            discord_url = discord_webhook

        html_message = ""
        try:
            for segment in event.conv_event.segments:
                if not segment:
                    html_message += "<br />"
                    continue
                else: 
                    html_message += markdownify(segment)

            logging.info("html_text: {}".format(html_message))
        except AttributeError:
            for segment in event.conv_event.ChatMessageSegment:
                if segment.type_ == hangups.schemas.SegmentType.TEXT:
                    html_message = event.text
        except TypeError:
            try:
                for segment in event.conv_event.segments:
                    if not segment:
                        html_message += "<br />"
                        continue
                    elif segment.type_ == hangups.schemas.SegmentType.TEXT:
                        html_message = event.text
                    else: 
                        html_message += markdownify(segment)
            except TypeError:
                for segment in event.conv_event.text:
                    if not segment:
                        html_message += "<br />"
                        continue
                    else: 
                        html_message = event.text

        body = {u"content":u"{}".format(html_message), u"username":u"{}".format(username), u"avatar_url":u"{}".format(avatar)}
        requests.post(discord_url, data=body)

def markdownify(segment):
    text = segment.text
    prefix = ""
    if segment.is_bold:
        prefix += "**"
    if segment.is_italic:
        prefix += "_"
    if segment.is_underline:
        prefix =+ "__"

    if prefix:
        suffix = prefix[::-1]
        text = prefix + text + suffix

    return text 
