import asyncio
import logging
import pprint

import plugins


logger = logging.getLogger(__name__)

pp = pprint.PrettyPrinter(indent=2)


def _initialise(bot):
    plugins.register_admin_command(["testcontext"])
    plugins.register_handler(_handle_incoming_message, type="allmessages")


def testcontext(bot, event, *args):
    """test annotation with some tags"""
    tags = [ 'text', 'longer-text', 'text with symbols:!@#$%^&*(){}' ]
    yield from bot.coro_send_message(
        event.conv_id,
        "this message has context - please see your console/log".format(tags),
        context = { "tags": tags,
                    "passthru": { "random_variable" : "hello world!",
                                  "some_dictionary" : { "var1" : "a",
                                                        "var2" : "b" }}})


@asyncio.coroutine
def _handle_incoming_message(bot, event, command):
    """BEWARE OF INFINITE MESSAGING LOOPS!

    all bot messages have context, and if you send a message here
    it will also have context, triggering this handler again"""

    # output to log
    if event.passthru:
        logger.info("passthru received: {}".format(event.passthru))
    if event.context:
        logger.info("context received: {}".format(event.context))

    # output to stdout
    if event.passthru:
        print("--- event.passthru")
        pp.pprint(event.passthru)
    if event.context:
        print("--- event.context")
        pp.pprint(event.context)
