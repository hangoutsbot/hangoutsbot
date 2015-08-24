"""
example plugin which demonstrates user and conversation memory
"""

import plugins


def _initialise(bot):
    plugins.register_admin_command(["rememberme", "whatme", "forgetme", "rememberchat", "whatchat", "forgetchat"])


def rememberme(bot, event, *args):
    """remember value for current user, memory must be empty.
    use /bot forgetme to clear previous storage
    """

    text = bot.user_memory_get(event.user.id_.chat_id, 'test_memory')
    if text is None:
        bot.user_memory_set(event.user.id_.chat_id, 'test_memory', ' '.join(args))
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b>, remembered!").format(
                event.user.full_name, text))
    else:
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b>, remembered something else!").format(
                event.user.full_name))


def whatme(bot, event, *args):
    """reply with value stored for current user"""

    text = bot.user_memory_get(event.user.id_.chat_id, 'test_memory')
    if text is None:
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b>, nothing remembered!").format(
                event.user.full_name))
    else:
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b> asked me to remember <i>\"{}\"</i>").format(
                event.user.full_name, text))


def forgetme(bot, event, *args):
    """forget stored value for current user"""

    text = bot.user_memory_get(event.user.id_.chat_id, 'test_memory')
    if text is None:
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b>, nothing to forget!").format(
                event.user.full_name))
    else:
        bot.user_memory_set(event.user.id_.chat_id, 'test_memory', None)
        yield from bot.coro_send_message(
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
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b>, remembered for this conversation").format(
                event.user.full_name, text))
    else:
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b>, remembered something else for this conversation!").format(
                event.user.full_name))


def whatchat(bot, event, *args):
    """reply with stored value for current conversation"""

    text = bot.conversation_memory_get(event.conv_id, 'test_memory')
    if text is None:
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b>, nothing remembered for this conversation!").format(
                event.user.full_name))
    else:
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b> asked me to remember <i>\"{}\" for this conversation</i>").format(
                event.user.full_name, text))


def forgetchat(bot, event, *args):
    """forget stored value for current conversation"""

    text = bot.conversation_memory_get(event.conv_id, 'test_memory')
    if text is None:
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b>, nothing to forget for this conversation!").format(
                event.user.full_name))
    else:
        bot.conversation_memory_set(event.conv_id, 'test_memory', None)
        yield from bot.coro_send_message(
            event.conv,
            _("<b>{}</b>, forgotten for this conversation!").format(
                event.user.full_name))
