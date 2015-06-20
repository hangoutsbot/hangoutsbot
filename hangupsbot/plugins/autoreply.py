import asyncio, re, logging
import json

from hangups.ui.utils import get_conv_name
import plugins

def _initialise(command):
    command.register_handler(_handle_autoreply)
    plugins.register_admin_command(["autoreply"])

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
                if _words_in_text(kw, event.text) or kw == "*":
                    bot.send_message_parsed(event.conv, sentence)
                    break

def _words_in_text(word, text):
    """Return True if word is in text"""

    regexword = "\\b" + word + "\\b"

    return True if re.search(regexword, text, re.IGNORECASE) else False

def autoreply(bot, event, cmd=None, *args):
    """adds or removes an autoreply.
    Format:
    /bot autoreply add [["question1","question2"],"answer"] // add an autoreply
    /bot autoreply remove [["question"],"answer"] // remove an autoreply
    /bot autoreply // view all autoreplies
    """

    path = ["autoreplies"]
    argument = " ".join(args)
    html = ""
    value = bot.config.get_by_path(path)

    if cmd == 'add':
        if isinstance(value, list):
            value.append(json.loads(argument))
            bot.config.set_by_path(path, value)
            bot.config.save()
        else:
            html = "Append failed on non-list"
    elif cmd == 'remove':
        if isinstance(value, list):
            value.remove(json.loads(argument))
            bot.config.set_by_path(path, value)
            bot.config.save()
        else:
            html = "Remove failed on non-list"

    if html == "":
        bot.config.load()
        value = bot.config.get_by_path(path)
        html = "<b>Autoreply config:</b> <br /> {}".format(value)

    bot.send_html_to_conversation(event.conv_id, html)
