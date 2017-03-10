"""
cleverbot hangoutsbot plugin
requires: https://pypi.python.org/pypi/cleverwrap
commands: chat, chatreset

configuration
-------------

set the cleverbot API key by saying:

/bot config set cleverbot_api_key "<API KEY>"

read more (and register) on the cleverbot API here:
    https://www.cleverbot.com/api/

config.json
-----------
* cleverbot_api_key
  * string cleverbot api key
* cleverbot_percentage_replies
  * integer between 0-100 for % chance of replying to a user message
* cleverbot_segregate
  * UNSET/True to keep cleverbot memory separate in each conversation
  * False to share memory between conversations
"""

import asyncio
import plugins
import logging

from random import randrange, randint

logger = logging.getLogger(__name__)

try:
    from cleverwrap import CleverWrap
except ImportError:
    logger.warning("required module: cleverwrap")

__cleverbots = {}


def _initialise(bot):
    plugins.register_handler(_handle_incoming_message, type="message")
    plugins.register_user_command(["chat"])
    plugins.register_admin_command(["chatreset"])


@asyncio.coroutine
def _handle_incoming_message(bot, event, command):
    """setting a global or per-conv cleverbot_percentage_replies config key
    will make this plugin intercept random messages to be sent to cleverbot"""

    if not event.text:
        return

    if not bot.get_config_suboption(event.conv_id, 'cleverbot_percentage_replies'):
        return

    percentage = bot.get_config_suboption(event.conv_id, 'cleverbot_percentage_replies')

    if randrange(0, 101, 1) < float(percentage):
        yield from chat(bot, event)


def _get_cw_for_chat(bot, event):
    """initialise/get cleverbot api wrapper"""

    # setting segregate to False makes cleverbot share its memory across non-segregated conversations
    # important: be careful of information leaking from one conversation to another!
    # by default, conversation memory is segregrated by instantiating new cleverwrap interfaces
    segregate = bot.get_config_suboption(event.conv_id, "cleverbot_segregate")
    if segregate is None:
        segregate = True
    if segregate:
        index = event.conv_id
    else:
        index = "shared"

    if index in __cleverbots:
        return __cleverbots[index]
    else:
        # dev: you can define different API keys for different conversations
        api_key = bot.get_config_suboption(event.conv_id, "cleverbot_api_key")
        if not api_key:
            return None
        else:
            cw = CleverWrap(api_key)
            __cleverbots[index] = cw
            logger.debug("created new cw for {}".format(index))
            return cw


def chat(bot, event, *args):
    """chat with cleverbot

    example: /bot chat hi cleverbot!"""

    cw = _get_cw_for_chat(bot, event)
    if not cw:
        response = "API key not defined: config.cleverbot_api_key"
        logger.error(response)
        yield from bot.coro_send_message(event.conv_id, response)
        return

    if args:
        input_text = " ".join(args)
    else:
        input_text = event.text

    # cw.say takes one argument, the input string. It is a blocking call that returns cleverbot's response.
    # see https://github.com/edwardslabs/cleverwrap.py for more information
    response = cw.say(input_text)

    yield from bot.coro_send_message(event.conv_id, response)


def chatreset(bot, event, *args):
    """tells cleverbot to forget things you've said in the past"""

    cw = _get_cw_for_chat(bot, event)
    if cw:
        cw.reset()
    yield from bot.coro_send_message(event.conv_id, "cleverbot has been reset!")
