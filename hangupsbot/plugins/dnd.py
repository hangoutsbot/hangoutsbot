import functools

def _initialise(Handlers, bot=None):
    if bot:
        _migrate_dnd_config_to_memory(bot)
    Handlers.register_object('dnd.user_check', functools.partial(_user_has_dnd, bot))
    Handlers.register_user_command(["dnd"])
    return []


def _migrate_dnd_config_to_memory(bot):
    # migrate DND list to memory.json
    if bot.config.exists(["donotdisturb"]):
        dndlist = bot.config.get("donotdisturb")
        bot.memory.set_by_path(["donotdisturb"], dndlist)
        del bot.config["donotdisturb"]
        bot.memory.save()
        bot.config.save()
        print("migration(): dnd list migrated")


def dnd(bot, event, *args):
    """allow users to toggle DND for ALL conversations (i.e. no @mentions)
        /bot dnd"""

    # ensure dndlist is initialised
    if not bot.memory.exists(["donotdisturb"]):
        bot.memory["donotdisturb"] = []

    initiator_chat_id = event.user.id_.chat_id
    dnd_list = bot.memory.get("donotdisturb")
    if initiator_chat_id in dnd_list:
        dnd_list.remove(initiator_chat_id)
    else:
        dnd_list.append(initiator_chat_id)

    bot.memory["donotdisturb"] = dnd_list
    bot.memory.save()

    if bot.call_shared("dnd.user_check", initiator_chat_id):
        bot.send_message_parsed(
            event.conv,
            "global DND toggled ON for {}".format(event.user.full_name))
    else:
        bot.send_message_parsed(
            event.conv,
            "global DND toggled OFF for {}".format(event.user.full_name))


def _user_has_dnd(bot, user_id):
    user_has_dnd = False
    if bot.memory.exists(["donotdisturb"]):
        donotdisturb = bot.memory.get('donotdisturb')
        if user_id in donotdisturb:
            user_has_dnd = True
    return user_has_dnd