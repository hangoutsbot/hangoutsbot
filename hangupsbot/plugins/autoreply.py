import asyncio, re, logging

from hangups.ui.utils import get_conv_name

""" Cache to keep track of what keywords are being watched. Listed by user_id """
keywords = {}

def _initialise(command):
    command.register_handler(_handle_autoreply)
    return []

@asyncio.coroutine
def _handle_autoreply(bot, event, command):

    autoreplies_enabled = bot.get_config_suboption(event.conv.id_, 'autoreplies_enabled')
    if not autoreplies_enabled:
        logging.info(_("autoreplies in {} disabled/unset").format(event.conv.id_))
        return


    """Handle autoreplies to keywords in messages"""

    autoreplies_list = bot.get_config_suboption(event.conv_id, 'autoreplies')
    if autoreplies_list:
        for kwds, sentence in autoreplies_list:
            for kw in kwds:
                if words_in_text(kw, event.text) or kw == "*":
                    bot.send_message_parsed(event.conv, sentence)
                    break

def words_in_text(word, text):
    """Return True if word is in text"""

    #TODO: This is identical to regex in line 33 of subscribe.py!

    regexword = "\\b" + word + "\\b"

    return True if re.search(regexword, text, re.IGNORECASE) else False
