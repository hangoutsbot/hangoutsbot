import asyncio, re, logging, unicodedata

from hangups.ui.utils import get_conv_name

""" Cache to keep track of what keywords are being watched. Listed by user_id """
keywords = {}

def _initialise(command):
    command.register_handler(_handle_autoreply)
    return

@asyncio.coroutine
def _handle_autoreply(bot, event, command):
    """Handle autoreplies to keywords in messages"""

    autoreplies_list = bot.get_config_suboption(event.conv_id, 'autoreplies')
    if autoreplies_list:
        for kwds, sentence in autoreplies_list:
            for kw in kwds:
                if words_in_text(kw, event.text) or kw == "*":
                    bot.send_message(event.conv, sentence)
                    break

def words_in_text(word, text):
    """Return True if word is in text"""
    # Transliterate unicode characters to ASCII and make everything lowercase
    word = unicodedata.normalize('NFKD', word).encode('ascii', 'ignore').decode().lower()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()

    # Replace delimiters in text with whitespace
    for delim in '.,:;!?':
        text = text.replace(delim, ' ')

    return True if word in text else False
