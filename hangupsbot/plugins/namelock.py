"""Allows the user to configure the bot to watch for hangout renames
and change the name back to a default name accordingly"""

import asyncio

import hangups

def _initialise(Handlers, bot=None):
    Handlers.register_handler(_watch_rename, type="rename")
    Handlers.register_admin_command(["topic"])
    return []


@asyncio.coroutine
def _watch_rename(bot, event, command):
    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return

    try:
        if not bot.memory.get_by_path(["conv_data", event.conv_id, "topic"]) == '':
            yield from bot._client.setchatname(event.conv_id, bot.memory.get_by_path(["conv_data", event.conv_id, "topic"]))
    except TypeError:
        """Memory file blank, continuing"""
        return
    except KeyError:
        """Path not specified, continuing"""
        return

def topic(bot, event, *args):
    """locks a conversation title. if no parameters supplied, clear and unlock the title"""

    topic = ' '.join(args).strip()

    bot.initialise_memory(event.conv_id, "conv_data")

    bot.memory.set_by_path(["conv_data", event.conv_id, "topic"], topic)

    bot.memory.save()

    if(topic == ''):
        bot.send_message(event.conv, _("Removing topic"))
    else:
        bot.send_message(
            event.conv,
            _("Setting topic to '{}'").format(topic))

    """Rename Hangout"""
    yield from bot._client.setchatname(event.conv_id, topic)
