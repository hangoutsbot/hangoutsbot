"""
example plugin that uses bot.user_memory_get and bot.user_memory_set
"""

"""user memory"""

def rememberthis(bot, event, *args):    
    text = bot.user_memory_get(event.user.id_.chat_id, 'test_memory')
    if text is None:
        bot.user_memory_set(event.user.id_.chat_id, 'test_memory', ' '.join(args))
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, remembered!".format(
                event.user.full_name, text))
    else:
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, remembered something else!".format(
                event.user.full_name))


def whatwasit(bot, event, *args):
    text = bot.user_memory_get(event.user.id_.chat_id, 'test_memory')
    if text is None:
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, nothing remembered!".format(
                event.user.full_name))
    else:
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b> asked me to remember <i>\"{}\"</i>".format(
                event.user.full_name, text))


def forgetaboutit(bot, event, *args):
    text = bot.user_memory_get(event.user.id_.chat_id, 'test_memory')
    if text is None:
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, nothing to forget!".format(
                event.user.full_name))
    else:
        bot.user_memory_set(event.user.id_.chat_id, 'test_memory', None)
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, forgotten!".format(
                event.user.full_name))

"""conversation memory"""

def conversationrememberthis(bot, event, *args):    
    text = bot.conversation_memory_get(event.conv_id, 'test_memory')
    if text is None:
        bot.conversation_memory_set(event.conv_id, 'test_memory', ' '.join(args))
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, remembered for this conversation".format(
                event.user.full_name, text))
    else:
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, remembered something else for this conversation!".format(
                event.user.full_name))


def conversationwhatwasit(bot, event, *args):
    text = bot.conversation_memory_get(event.conv_id, 'test_memory')
    if text is None:
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, nothing remembered for this conversation!".format(
                event.user.full_name))
    else:
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b> asked me to remember <i>\"{}\" for this conversation</i>".format(
                event.user.full_name, text))

def conversationforgetaboutit(bot, event, *args):
    text = bot.conversation_memory_get(event.conv_id, 'test_memory')
    if text is None:
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, nothing to forget for this conversation!".format(
                event.user.full_name))
    else:
        bot.conversation_memory_set(event.conv_id, 'test_memory', None)
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, forgotten for this conversation!".format(
                event.user.full_name))