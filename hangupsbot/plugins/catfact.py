import logging
import plugins
import requests

logger = logging.getLogger(__name__)

def _initialise(bot):
    plugins.register_user_command(["catfact"])

def catfact(bot, event, number=1):
    try:
        r = requests.get("http://catfacts-api.appspot.com/api/facts?number={}".format(number))
        html_text = '<br>'.join(r.json()['facts'])
    except:
        html_text = "Unable to get catfacts right now"
        logger.exception(html_text)

    yield from bot.coro_send_message(event.conv_id, html_text)
