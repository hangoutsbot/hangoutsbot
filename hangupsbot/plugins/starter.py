def whoareyou(bot, event, *args):
    print(bot.user_self())

def iamspartacus(bot, event, *args):
    admin_key = "admins"
    global_admins = bot.get_config_option(admin_key)
    if not global_admins:
        chat_id = event.user_id.chat_id
        bot.send_message_parsed(event.conv, 
            '<i>Starter: Configuring first admin: {}</i>'.format(chat_id))
        initial_admin_list = [chat_id]
        bot.config[admin_key] = initial_admin_list
        bot.config.save()
    else:
        bot.send_message_parsed(event.conv, "<i>No! I am Spartacus!</i>")