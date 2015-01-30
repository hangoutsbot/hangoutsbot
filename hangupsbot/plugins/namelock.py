"""Allows the user to configure the bot to watch for hangout renames
and change the name back to a default name accordingly"""

import asyncio

import hangups

def _initialise(command):
    command.register_handler(_handle_rename)
    return ["topic"]

@asyncio.coroutine
def _handle_rename(bot, event, command):
    """handle renames"""
    print("Handling rename!")
    if isinstance(event, hangups.RenameEvent):
        yield from bot._client.setchatname(event.conv_id, bot.memory.get_by_path(["conv_data", event.conv_id, "topic"]))

def topic(bot, event, *args):
    """Set a chat topic. If no parameters given, remove the topic"""

    topic = ' '.join(args).strip()

    bot.initialise_memory(event.conv_id, "conv_data")

    bot.memory.set_by_path(["conv_data", event.conv_id, "topic"], topic)

    bot.memory.save()

    if(topic == ''):
        bot.send_message_parsed(event.conv, "Removing topic")
    else:
        bot.send_message_parsed(
            event.conv,
            "Setting topic to '{}'".format(topic))

    """Rename Hangout"""
    yield from bot._client.setchatname(event.conv_id, topic)
