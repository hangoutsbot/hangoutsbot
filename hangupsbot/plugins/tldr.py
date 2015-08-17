import time

import plugins


def _initialise(bot):
    plugins.register_user_command(["tldr"])


def tldr(bot, event, *args):
    """Adds a short message to a list saved for the conversation using:
    /bot tldr <message>
    All TLDRs can be retrieved by /bot tldr (without any parameters)
    All TLDRs can be deleted using /bot tldr clear, single tldr with /bot clear <number>"""

    if not bot.memory.exists(['tldr']):
        bot.memory.set_by_path(['tldr'], {})

    if not bot.memory.exists(['tldr', event.conv_id]):
        bot.memory.set_by_path(['tldr', event.conv_id], {})

    conv_tldr = bot.memory.get_by_path(['tldr', event.conv_id])

    if not args:
        # Display all messages
        if len(conv_tldr) > 0:
            html = []
            html.append(_("<b>TL;DR ({}):</b>").format(len(conv_tldr)))
            for i, timestamp in enumerate(sorted(conv_tldr, key=float)):
                html.append(_("{}. {} <b>{} ago</b>").format( str(i+1),
                                                             conv_tldr[timestamp],
                                                             _time_ago(float(timestamp)) ))

            yield from bot.coro_send_message(event.conv_id, "<br />".join(html))

        else:
            yield from bot.coro_send_message(event.conv_id, _("Nothing in TL;DR"))

        return

    if "clear" in args[0]:
        if len(args) >= 2 and args[1].isdigit():
            sorted_keys = sorted(list(conv_tldr.keys()), key=float)
            key_index = int(args[1]) - 1
            if key_index < 0 or key_index >= len(sorted_keys):
                message = _("TL;DR #{} not found").format(args[1])
            else:
                popped_tldr = conv_tldr.pop(sorted_keys[key_index])
                bot.memory.set_by_path(['tldr', event.conv_id], conv_tldr)
                message = _('TL;DR #{} removed - "{}"').format(args[1], popped_tldr)
        else:
            bot.memory.set_by_path(['tldr', event.conv_id], {})
            message = _("All TL;DRs cleared")

        yield from bot.coro_send_message(event.conv_id, message)

    else:
        tldr = ' '.join(args).replace("'", "").replace('"', '')

        if tldr:
            # Add message to list
            conv_tldr[str(time.time())] = tldr
            bot.memory.set_by_path(['tldr', event.conv_id], conv_tldr)
            yield from bot.coro_send_message( event.conv_id,
                                              _('Added "{}" to TL;DR. Count: {}').format( tldr,
                                                                                          len(conv_tldr) ))

    bot.memory.save()


def _time_ago(timestamp):
    time_difference = time.time() - timestamp
    if time_difference < 60: # seconds
        return _("{}s").format(int(time_difference))
    elif time_difference < 60*60: # minutes
        return _("{}m").format(int(time_difference/60))
    elif time_difference < 60*60*24: # hours
        return _("{}h").format(int(time_difference/(60*60)))
    else:
        return _("{}d").format(int(time_difference/(60*60*24)))
