import hangups
import time

import plugins


def _initialise(bot):
    plugins.register_user_command(["tldr"])


def tldr(bot, event, *args):
    """Adds a short message to a list saved for the conversation using:
    /bot tldr <message>
    All tldr's can be retrieved by /bot tldr (without any parameters)
    tldr's can be deleted using /bot tldr clear"""

    tldr = ' '.join(args).replace("'", "")

    # Initialize tldr for chat (or if 'clear' argument is passed)
    if not bot.memory.exists(['tldr']):
        bot.memory.set_by_path(['tldr'], {})
    if not bot.memory.exists(['tldr', event.conv_id]) or "clear" in tldr:
        bot.memory.set_by_path(['tldr', event.conv_id], {})
        if "clear" in tldr:
            bot.send_html_to_conversation(event.conv_id, "TL;DR cleared")
            bot.memory.save()
            return

    chat_tldr = bot.memory.get_by_path(['tldr', event.conv_id])

    if tldr: # Add message to list
        chat_tldr[time.time()] = tldr
        bot.memory.set_by_path(['tldr', event.conv_id], chat_tldr)
        bot.send_html_to_conversation(event.conv_id, "Added '{}' to TL;DR. Now at {} entires".format(tldr, len(chat_tldr)))
    else: # Display all messages
        if len(chat_tldr) > 0:
            html = "<b>TL;DR ({} entries):</b><br />".format(len(chat_tldr))
            for timestamp in sorted(chat_tldr):
                html += "* {} <b>{} ago</b><br />".format(chat_tldr[timestamp], _time_ago(float(timestamp)))
            bot.send_html_to_conversation(event.conv_id, html)

        else:
            bot.send_html_to_conversation(event.conv_id, "Nothing in TL;DR")

    bot.memory.save()

def _time_ago(timestamp):
    time_difference = time.time() - timestamp
    if time_difference < 60: # seconds
        return "{}s".format(int(time_difference))
    elif time_difference < 60*60: # minutes
        return "{}m".format(int(time_difference/60))
    elif time_difference < 60*60*24: # hours
        return "{}h".format(int(time_difference/(60*60)))
    else:
        return "{}d".format(int(time_difference/(60*60*24)))
