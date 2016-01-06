import logging
import plugins
import requests

logger = logging.getLogger(__name__)

def _initialise(bot):
    plugins.register_user_command(["catfact"])

def catfact(bot, event, *args):
    try:
        r = requests.get("http://catfacts-api.appspot.com/api/facts?number=1")
        html_text = r.json()['facts'][0]
    except:
        html_text = "Unable to get catfacts right now"
        logger.exception(html_text)

    yield from bot.coro_send_message(event.conv_id, html_text)
