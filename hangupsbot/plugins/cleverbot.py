# Set your API key by saying
# /bot config set cleverbot-api-key "EXAMPLE_API_KEY_REPLACE_THIS"
# to your bot

from cleverwrap import CleverWrap
from random import randrange, randint
import asyncio
import plugins
import logging

logger = logging.getLogger(__name__)
cw = None

def _initialise(bot):
    plugins.register_handler(_handle_incoming_message, type="message")
    plugins.register_user_command(["chat"])
    plugins.register_admin_command(["chatreset"])
    api_key = bot.get_config_option("cleverbot-api-key")
    if not api_key:
        logger.error("No cleverbot API key defined")
    else:
        global cw
        cw = CleverWrap(api_key)

@asyncio.coroutine
def _handle_incoming_message(bot, event, command):
    """Handle random message intercepting"""

    if not event.text:
        return

    if not bot.get_config_suboption(event.conv_id, 'cleverbot_percentage_replies'):
        return

    if not cw:
        return

    percentage = bot.get_config_suboption(event.conv_id, 'cleverbot_percentage_replies')

    if randrange(0, 101, 1) < float(percentage):
        text = cw.say(event.text)
        if text:
            yield from bot.coro_send_message(event.conv_id, text)


def chat(bot, event, *args):
    if not cw:
        yield from bot.coro_send_message(event.conv_id, "API key not defined")
    else:
        text = cw.say(event.text)
        yield from bot.coro_send_message(event.conv_id, text)


def chatreset(bot, event, *args):
    cw.reset()
    yield from bot.coro_send_message(event.conv_id, "reset")