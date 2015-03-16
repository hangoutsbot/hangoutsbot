"""
add aliases for the bot
"""

def _initialise(Handlers, bot=None):
    bot_command_aliases = ["/bot"] # basic

    myself = bot.user_self()

    # /<first name fragment>
    first_fragment = myself["full_name"].split()[0].lower()
    if first_fragment and first_fragment != "unknown":
        alias_firstname = "/" + first_fragment
        bot_command_aliases.append(alias_firstname)

    # /<chat_id>
    bot_command_aliases.append("/" + myself["chat_id"])

    print("bot aliases: {}".format(bot_command_aliases))

    Handlers.bot_command = bot_command_aliases