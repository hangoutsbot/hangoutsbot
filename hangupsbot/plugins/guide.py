"""
plugin that makes the bot a 'guide'
"""

def guide(bot, event, *args):
    text = bot.user_memory_get(event.user.id_.chat_id, 'guideprogress')
    if text is None:
        bot.user_memory_set(event.user.id_.chat_id, 'guideprogress', '0')
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, remembered!".format(
                event.user.full_name, text))
    else:
        bot.send_message_parsed(
            event.conv,
            "<b>{}</b>, remembered something else!".format(
                event.user.full_name))

def next(bot, event, *args):
    text = bot.user_memory_get(event.user.id_.chat_id, 'guideprogress')
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
