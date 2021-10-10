import time
import plugins
import requests
import hangups
import logging
import random

logger = logging.getLogger(__name__)

def _initialise(bot):
    plugins.register_user_command(["copypasta"])

def copypasta(bot, event, *args):
    try:
        r = requests.get("https://www.reddit.com/r/copypasta/new/.json?sort=top&t=week&showmedia=false&mediaonly=false&is_self=true&limit=100", headers = {'User-agent': 'your bot 0.1'})
        pastas = r.json()['data']['children'][random.randint(0, 99)]['data']['selftext']
    except:
        pastas = "Unable to get copypastas right now"
        logger.exception(pastas)

    yield from bot.coro_send_message(event.conv_id, pastas)
