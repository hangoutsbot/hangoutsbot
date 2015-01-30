"""Allows the user to configure the bot to watch for hangout renames
and change the name back to a default name accordingly"""

def setchatname(bot, event, *args):
    """Set a chat name. If no parameters given, remove chat name"""

    truncatelength = 32 # What should the maximum length of the chatroom be?
    chatname = ' '.join(args).strip()
    chatname = chatname[0:truncatelength]

    bot.initialise_memory(event.conv_id, "conv_data")

    bot.memory.set_by_path(["conv_data", event.conv_id, "chatname"], chatname)

    bot.memory.save()

    if(chatname == ''):
        bot.send_message_parsed(event.conv, "Removing chatname")
    else:
        bot.send_message_parsed(
            event.conv,
            "Setting chatname to '{}'".format(chatname))
