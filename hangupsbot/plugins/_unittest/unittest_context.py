import asyncio

import plugins


def _initialise(bot):
    plugins.register_admin_command(["testcontext"])
    plugins.register_handler(_handle_incoming_message, type="allmessages")


def testcontext(bot, event, *args):
    """test annotation with some tags"""
    tags = [ 'text', 'longer-text', 'text with symbols:!@#$%^&*(){}' ]
    yield from bot.coro_send_message(
        event.conv_id,
        "this message has tags: {}".format(tags),
        context = { "tags": tags })


@asyncio.coroutine
def _handle_incoming_message(bot, event, command):
    if event.tags:
        yield from bot.coro_send_message(event.conv_id, "to Google and back!: {}".format(event.tags))
