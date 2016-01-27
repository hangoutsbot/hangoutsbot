import plugins
import asyncio

def _initialise(bot):
    plugins.register_user_command(["remindme","remindall"])

def remindme(bot, event, dly, *args):
    """
    Posts a custom message to a 1on1 after a delay

    /bot remindme <b>delay (minutes)</b> <i>Message</i>
    """

    if not args:
        yield from bot.coro_send_message(event.conv, _("Usage: /bot remindme <b>delay (minutes)</b> <i>Message</i>"))
        return

    try:
        delayTime = float(dly)*60.0
        yield from bot.coro_send_message(event.conv, _("Private reminder for <b>{}</b> in {}m").format(event.user.full_name, dly))
        conv_1on1 = yield from bot.get_1to1(event.user.id_.chat_id)
        yield from asyncio.sleep(delayTime)
        yield from bot.coro_send_message(event.conv, _("<b>Reminder:</b> " + " ".join(str(x) for x in args)))
    except ValueError:
        yield from bot.coro_send_message(event.conv, _("Error creating reminder, invalid delay"))


def remindall(bot, event, dly, *args):
    """
    Posts a custom message to the chat after a delay

    /bot remindall <b>delay (minutes)</b> <i>Message</i>
    """

    if not args:
        yield from bot.coro_send_message(event.conv, _("Usage: /bot remindall <b>delay (minutes)</b> <i>Message</i>"))
        return

    try:
        delayTime = float(dly)*60.0
        yield from bot.coro_send_message(event.conv, _("Public reminder in {}m").format(dly))
        yield from asyncio.sleep(delayTime)
        yield from bot.coro_send_message(event.conv, _("<b>Reminder:</b> " + " ".join(str(x) for x in args)))
    except ValueError:
        yield from bot.coro_send_message(event.conv, _("Error creating reminder, invalid delay"))
