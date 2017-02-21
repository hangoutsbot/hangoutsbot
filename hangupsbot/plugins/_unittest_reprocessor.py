import asyncio

import hangups

import plugins


def _initialise(bot):
    plugins.register_admin_command(["testcoroutinecontext", "testnoncoroutinecontext"])


def testcoroutinecontext(bot, event, *args):
    """test hidden context"""
    yield from bot.coro_send_message(
        event.conv_id,
        "This message has hidden context",
        context = { "reprocessor": bot.call_shared( "reprocessor.attach_reprocessor",
                                                    coro_reprocess_the_event,
                                                    return_as_dict=True )})


def testnoncoroutinecontext(bot, event, *args):
    """test hidden context"""
    yield from bot.coro_send_message(
        event.conv_id,
        "This message has hidden context",
        context = { "reprocessor": bot.call_shared( "reprocessor.attach_reprocessor",
                                                    reprocess_the_event,
                                                    return_as_dict=True )})


@asyncio.coroutine
def coro_reprocess_the_event(bot, event, id):
    yield from bot.coro_send_message(
        event.conv_id,
        """<em>coroutine responding to message with uuid: {}</em><br />"""
        """VISIBLE CONTENT WAS: {}""".format(id, event.text))


def reprocess_the_event(bot, event, id):
    asyncio.async(
        bot.coro_send_message(
            event.conv_id,
            """<em>non-coroutine responding to message with uuid: {}</em><br />"""
            """VISIBLE CONTENT WAS: {}""".format(id, event.text))
    ).add_done_callback(lambda future: future.result())
