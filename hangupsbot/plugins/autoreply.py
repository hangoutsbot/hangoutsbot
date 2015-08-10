import asyncio, re, logging, json, random

import plugins


logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_handler(_handle_autoreply, type="message")
    plugins.register_admin_command(["autoreply"])


def _handle_autoreply(bot, event, command):
    config_autoreplies = bot.get_config_suboption(event.conv.id_, 'autoreplies_enabled')
    tagged_autoreplies = "autoreplies-enable" in bot.tags.useractive(event.user_id.chat_id, event.conv.id_)

    if not (config_autoreplies or tagged_autoreplies):
        return

    if "autoreplies-disable" in bot.tags.useractive(event.user_id.chat_id, event.conv.id_):
        logger.debug("explicitly disabled by tag for {} {}".format(event.user_id.chat_id, event.conv.id_))
        return

    """Handle autoreplies to keywords in messages"""

    autoreplies_list = bot.get_config_suboption(event.conv_id, 'autoreplies')
    if autoreplies_list:
        for kwds, sentences in autoreplies_list:
            for kw in kwds:
                if _words_in_text(kw, event.text) or kw == "*":
                    if isinstance(sentences, list):
                        message = random.choice(sentences)
                    else:
                        message = sentences

                    logger.info("matched: {}".format(kw))
                    yield from bot.coro_send_message(event.conv, message)
                    break


def _words_in_text(word, text):
    """Return True if word is in text"""

    if word.startswith("regex:"):
        word = word[6:]
    else:
        word = re.escape(word)

    regexword = "(?<!\w)" + word + "(?!\w)"

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

    # Reload the config
    bot.config.load()

    if html == "":
        value = bot.config.get_by_path(path)
        html = "<b>Autoreply config:</b> <br /> {}".format(value)

    yield from bot.coro_send_message(event.conv_id, html)
