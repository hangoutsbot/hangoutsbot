def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["addmod", "delmod"])

def addmod(bot, event, *args):
    mod_ids = list(args)
    if(bot.get_config_suboption(event.conv_id, 'mods') != None):
        for mod in bot.get_config_suboption(event.conv_id, 'mods'):
            mod_ids.append(mod)
        bot.config.set_by_path(["mods"], mod_ids)
        bot.config.save()
        html_message = _("<i>Moderators updated: {} added</i>")
        bot.send_message_parsed(event.conv, html_message.format(args[0]))
    else:
        bot.config.set_by_path(["mods"], mod_ids)
        bot.config.save()
        html_message = _("<i>Moderators updated: {} added</i>")
        bot.send_message_parsed(event.conv, html_message.format(args[0]))
		
def delmod(bot, event, *args):
    if not bot.get_config_option('mods'):
        return
    
    mods = bot.get_config_option('mods')
    mods_new = []
    for mod in mods:
        if args[0] != mod:
            mods_new.append(mod)
    
    bot.config.set_by_path(["mods"], mods_new)
    bot.config.save()
    html_message = _("<i>Moderators updated: {} removed</i>")
    bot.send_message_parsed(event.conv, html_message.format(args[0]))