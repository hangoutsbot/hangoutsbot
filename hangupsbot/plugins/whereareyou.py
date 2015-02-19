from hangups.ui.utils import get_conv_name


def whereareyou(bot, event, *args):
    """list all active hangouts the bot is participating in by conversation name and ID"""

    line = "<b>list of active hangouts:</b><br />"

    for c in bot.list_conversations():
        line = line + "{}: {}".format(get_conv_name(c, truncate=True), c.id_)
        line = line + "<br />"
        line = line + "-"*len(c.id_) + "<br />"

    bot.send_message_parsed(event.conv, line)
