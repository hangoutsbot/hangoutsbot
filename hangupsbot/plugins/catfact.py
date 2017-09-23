import logging
import plugins
import requests

logger = logging.getLogger(__name__)

def _initialise(bot):
    plugins.register_user_command(["catfact"])

def catfact(bot, event):
    try:
        r = requests.get("https://catfact.ninja/fact")
        html_text = '<br>'.join(r.json()['fact'])
    except:
        html_text = "Unable to get cat facts right meow."
        logger.exception(html_text)

    yield from bot.coro_send_message(event.conv_id, html_text)
    
