import plugins

def _initialise(bot):
    plugins.register_admin_command(["dumpconv"])


def dumpconv(bot, event, *args):
    """dump all conversations known to the bot"""
    text_search = " ".join(args)
    lines = []
    all_conversations = bot.conversations.get().items()
    for convid, convdata in all_conversations:
        if text_search.lower() in convdata["title"].lower():
            lines.append("{} <em>{}</em> {}<br />... <b>{}</b> {}".format(convid, convdata["source"], len(convdata["users"]), convdata["title"], convdata["type"]))
    lines.append("<b><em>Totals: {}/{}</em></b>".format(len(lines), len(all_conversations)))
    bot.send_message_parsed(event.conv, "<br />".join(lines))
