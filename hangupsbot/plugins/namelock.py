"""Allows the user to configure the bot to watch for hangout renames
and change the name back to a default name accordingly"""

def topic(bot, event, *args):
    """Set a chat topic. If no parameters given, remove the topic"""

    topic = ' '.join(args).strip()

    bot.initialise_memory(event.conv_id, "conv_data")

    bot.memory.set_by_path(["conv_data", event.conv_id, "topic"], topic)

    bot.memory.save()

    if(chatname == ''):
        bot.send_message_parsed(event.conv, "Removing topic")
    else:
        bot.send_message_parsed(
            event.conv,
            "Setting topic to '{}'".format(topic))

    """Rename Hangout"""
    yield from bot._client.setchatname(event.conv_id, ' '.join(args))
