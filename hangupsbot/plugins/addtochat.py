import asyncio

def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["newchat"])
    Handlers.register_user_command(["addme"])
    return []

def newchat(bot, event, *args):
    """ Create a new chat """
    bot.conversation_memory_set(event.conv_id, "linkedchatname", ' '.join(args))
    bot.send_html_to_conversation(event.conv_id, "<i>{} created</i><br />To join the chat, type '<b>/bot addme</b>'".format(' '.join(args)))

def addme(bot, event, *args):

    user_ids = list()
    chatname = bot.conversation_memory_get(event.conv_id, "linkedchatname")
    if chatname is None:
        bot.send_html_to_conversation(event.conv_id, "<b>Error:</b> No linked chats")
        return

    current_conv_id = bot.conversation_memory_get(event.conv_id, "linkedconv_id")
    if current_conv_id is None: # Chat has not been created yet

        if not bot.memory.exists(["conv_data", event.conv_id, "linkedchatusers"]):
            # create the datatype if it does not exist
            user_ids = event.user.id_.chat_id
            bot.memory.set_by_path(["conv_data", event.conv_id, "linkedchatusers"], [user_ids])
        else:
            user_ids = bot.memory.get_by_path(["conv_data", event.conv_id, "linkedchatusers"])
            user_ids.append(event.user.id_.chat_id)
            bot.memory.set_by_path(["conv_data", event.conv_id, "linkedchatusers"], [user_ids])

        if len(user_ids) >= 2:
            print("length: {}, {}".format(len(user_ids), user_ids))
            response = yield from bot._client.createconversation(user_ids)
            current_conv_id = response['conversation']['id']['id']
            bot.conversation_memory_set(event.conv_id, "linkedconv_id", current_conv_id)
            bot.send_html_to_conversation(current_conv_id, "<i>Chat created</i>")
            yield from bot._client.setchatname(current_conv_id, chatname)

    else:
        yield from bot._client.adduser(current_conv_id, event.user.id_.chat_id)

    bot.send_html_to_conversation(event.conv_id, "<i>{} added to <b>{}</b></i>".format(event.user.full_name, chatname))


    current_conv_id = event.conv_id
    print("addusers: {}".format(user_ids))
    yield from bot._client.adduser(current_conv_id, user_ids)
