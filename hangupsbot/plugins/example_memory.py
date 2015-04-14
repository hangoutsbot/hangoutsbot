"""
example plugin which demonstrates user and conversation memory
"""

def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["rememberme", "whatme", "forgetme", "rememberchat", "whatchat", "forgetchat"])
    return []


def rememberme(bot, event, *args):
    """remember value for current user, memory must be empty.
    use /bot forgetme to clear previous storage
    """

    text = bot.user_memory_get(event.user.id_.chat_id, 'test_memory')
    if text is None:
        bot.user_memory_set(event.user.id_.chat_id, 'test_memory', ' '.join(args))
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, remembered!").format(
                event.user.full_name, text))
    else:
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, remembered something else!").format(
                event.user.full_name))


def whatme(bot, event, *args):
    """reply with value stored for current user"""

    text = bot.user_memory_get(event.user.id_.chat_id, 'test_memory')
    if text is None:
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, nothing remembered!").format(
                event.user.full_name))
    else:
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b> asked me to remember <i>\"{}\"</i>").format(
                event.user.full_name, text))


def forgetme(bot, event, *args):
    """forget stored value for current user"""

    text = bot.user_memory_get(event.user.id_.chat_id, 'test_memory')
    if text is None:
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, nothing to forget!").format(
                event.user.full_name))
    else:
        bot.user_memory_set(event.user.id_.chat_id, 'test_memory', None)
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, forgotten!").format(
                event.user.full_name))


"""conversation memory"""

def rememberchat(bot, event, *args):
    """remember value for current conversation, memory must be empty.
    use /bot forgetchat to clear previous storage
    """

    text = bot.conversation_memory_get(event.conv_id, 'test_memory')
    if text is None:
        bot.conversation_memory_set(event.conv_id, 'test_memory', ' '.join(args))
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, remembered for this conversation").format(
                event.user.full_name, text))
    else:
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, remembered something else for this conversation!").format(
                event.user.full_name))


def whatchat(bot, event, *args):
    """reply with stored value for current conversation"""

    text = bot.conversation_memory_get(event.conv_id, 'test_memory')
    if text is None:
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, nothing remembered for this conversation!").format(
                event.user.full_name))
    else:
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b> asked me to remember <i>\"{}\" for this conversation</i>").format(
                event.user.full_name, text))


def forgetchat(bot, event, *args):
    """forget stored value for current conversation"""

    text = bot.conversation_memory_get(event.conv_id, 'test_memory')
    if text is None:
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, nothing to forget for this conversation!").format(
                event.user.full_name))
    else:
        bot.conversation_memory_set(event.conv_id, 'test_memory', None)
        bot.send_message_parsed(
            event.conv,
            _("<b>{}</b>, forgotten for this conversation!").format(
                event.user.full_name))
