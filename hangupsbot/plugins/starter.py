import plugins


def _initialise(bot):
    plugins.register_admin_command(["files", "test_one2one_message"])
    plugins.register_user_command(["iamspartacus", "verifyme"])


def iamspartacus(bot, event, *args):
    """announce to the bot that you are spartacus"""
    admin_key = "admins"
    global_admins = bot.get_config_option(admin_key)
    if not global_admins:
        chat_id = event.user_id.chat_id
        bot.send_message_parsed(event.conv,
            _('<i>Starter: Configuring first admin: {}</i>').format(chat_id))
        initial_admin_list = [chat_id]
        bot.config[admin_key] = initial_admin_list
        bot.config.save()
    else:
        bot.send_message_parsed(event.conv, _("<i>No! I am Spartacus!</i>"))


def files(bot, event, *args):
    """list bot file paths"""
    one2one = bot.get_1on1_conversation(event.user.id_.chat_id)
    if one2one:
        bot.send_message_parsed(one2one,
            _('<i>config: {}<br />memory: {}</i>').format(
                bot.config.filename,
                bot.memory.filename))
    else:
        _one2one_required(bot, event.conv)


def verifyme(bot, event, *args):
    """verify that the user has a 1-to-1 conversation with the bot.
    optionally, supply a user chat id to test a user other than yourself.
    """

    if len(args) == 0:
        chat_id = event.user.id_.chat_id
    else:
        chat_id = " ".join(args)

    one2one = bot.get_1on1_conversation(chat_id)
    if one2one:
        if event.user_id.chat_id == chat_id:
            """send a private message only if the actual user requested it"""
            bot.send_message_parsed(one2one,
                _('<i>verification completed - this is your one-to-one chat with the bot</i>'))

        if event.conv_id != one2one.id_:
            """announce verification wherever it was requested"""
            bot.send_message_parsed(event.conv,
                _('<i>verified - user has a one-to-one conversation with me</i>'))
    else:
        """provide standard instructions if no one-2-one exists"""
        _one2one_required(bot, event.conv)


def test_one2one_message(bot, event, *args):
    """send a test message instructing the user to open a 1-to-1 hangout with the bot"""
    _one2one_required(bot, event.conv_id)


def _one2one_required(bot, target_conversation):
    myself = bot.user_self()
    bot.send_message_parsed(target_conversation,
        (_('<i>User must say "hi" to me first via a 1-on-1 hangout with <b>{}</b>.') +
         _('Then let me know by sending <b>/bot verifyme</b> in this chat.</i>')).format(
            myself["email"]))
