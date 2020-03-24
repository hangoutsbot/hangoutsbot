import logging
import plugins
import requests

logger = logging.getLogger(__name__)

def _initialise(bot):
    plugins.register_user_command(["covid19"])
    
def covid19(bot, event, *args):
    """reply to a ping"""
    try:   
        page = requests.get('https://coronavirus-19-api.herokuapp.com/all')
        pagearray = json.loads(page.text)
        cases = str(pagearray["cases"])
        deaths = str(pagearray["deaths"])
        html_text = "The COVID-19 outbreak has " + cases + " cases and " + deaths + "$
    except:
        html_text = "Unable to get covid-19 data right now"
        logger.exception(html_text)
    yield from bot.coro_send_message(event.conv_id, html_text)
