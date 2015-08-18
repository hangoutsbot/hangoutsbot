import asyncio, re, logging, json, random

import hangups

import plugins


logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_handler(_handle_autoreply, type="message")
    plugins.register_handler(_handle_autoreply, type="membership")
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

    if isinstance(event.conv_event, hangups.ChatMessageEvent):
        event_type = "MESSAGE"
    elif isinstance(event.conv_event, hangups.MembershipChangeEvent):
        if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
            event_type = "JOIN"
        else:
            event_type = "LEAVE"
    elif isinstance(event.conv_event, hangups.RenameEvent):
        event_type = "RENAME"
    else:
        raise RuntimeError("unhandled event type")

    autoreplies_list = bot.get_config_suboption(event.conv_id, 'autoreplies')
    if autoreplies_list:
        for kwds, sentences in autoreplies_list:

            if isinstance(sentences, list):
                message = random.choice(sentences)
            else:
                message = sentences

            if isinstance(kwds, list):
                for kw in kwds:
                    if _words_in_text(kw, event.text) or kw == "*":
                        logger.info("matched chat: {}".format(kw))
                        yield from send_reply(bot, event, message)
                        break

            elif event_type == kwds:
                logger.info("matched event: {}".format(kwds))
                yield from send_reply(bot, event, message)


@asyncio.coroutine
def send_reply(bot, event, message):
    values = { "event": event,
               "conv_title": bot.conversations.get_name( event.conv,
                                                         fallback_string=_("Unidentified Conversation") )}

    if "participant_ids" in dir(event.conv_event):
        values["participants"] = [ event.conv.get_user(user_id)
                                   for user_id in event.conv_event.participant_ids ]
        values["participants_namelist"] = ", ".join([ u.full_name for u in values["participants"] ])

    envelopes = []

    if message.startswith(("ONE_TO_ONE:", "HOST_ONE_TO_ONE")):
        message = message[message.index(":")+1:].strip()
        target_conv = yield from bot.get_1to1(event.user.id_.chat_id)
        if not target_conv:
            logger.error("1-to-1 unavailable for {} ({})".format( event.user.full_name,
                                                                  event.user.id_.chat_id ))
            return False
        envelopes.append((target_conv, message.format(**values)))

    elif message.startswith("GUEST_ONE_TO_ONE:"):
        message = message[message.index(":")+1:].strip()
        for guest in values["participants"]:
            target_conv = yield from bot.get_1to1(guest.id_.chat_id)
            if not target_conv:
                logger.error("1-to-1 unavailable for {} ({})".format( guest.full_name,
                                                                      guest.id_.chat_id ))
                return False
            values["guest"] = guest # add the guest as extra info
            envelopes.append((target_conv, message.format(**values)))

    else:
        envelopes.append((event.conv, message.format(**values)))

    for send in envelopes:
        yield from bot.coro_send_message(*send)

    return True


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
