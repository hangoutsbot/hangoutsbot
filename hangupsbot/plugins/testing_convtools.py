import asyncio

def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["addusers", "createconversation"])
    return []

def addusers(bot, event, *args):
    user_ids = list(set(args))
    current_conv_id = event.conv_id
    print("addusers: {}".format(user_ids))
    yield from bot._client.adduser(current_conv_id, user_ids)

def createconversation(bot, event, *args):
    user_ids = list(set(args))
    print("createconversation: {}".format(user_ids))
    response = yield from bot._client.createconversation(user_ids)
    new_conversation_id = response['conversation']['id']['id']
    bot.send_html_to_conversation(new_conversation_id, "<i>conversation created</i>")
