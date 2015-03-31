import asyncio
import random
import string

_externals = {
    "authorisation": False
}


def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["addusers", "createconversation", "refresh"])
    return []


def addusers(bot, event, *args):
    list_add = []
    target_conv = event.conv_id

    state = ["adduser"]

    for parameter in args:
        if parameter == "into":
            state.append("targetconv")
        else:
            if state[-1] == "adduser":
                list_add.append(parameter)
            elif state[-1] == "targetconv":
                target_conv = parameter
                state[-1] = "adduser"
            else:
                raise ValueError("UNKNOWN STATE: {}".format(state[-1]))

    list_add = list(set(list_add))
    print("addusers: {} into conversation {}".format(list_add, target_conv))
    if len(list_add) > 0:
        yield from bot._client.adduser(target_conv, list_add)


def createconversation(bot, event, *args):
    user_ids = list(set(args))
    print("createconversation: {}".format(user_ids))
    response = yield from bot._client.createconversation(user_ids)
    new_conversation_id = response['conversation']['id']['id']
    bot.send_html_to_conversation(new_conversation_id, "<i>conversation created</i>")


def refresh(bot, event, *args):
    parameters = list(set(args))
    if _externals["authorisation"] not in parameters:
        _externals["authorisation"] = False
        initiator_1on1 = bot.get_1on1_conversation(event.user.id_.chat_id)
        if initiator_1on1:
            _externals["authorisation"] = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(8))
            bot.send_html_to_conversation(initiator_1on1, "<i>are you sure? execute the command again and append this key: {}</i>".format(_externals["authorisation"]))
        else:
            bot.send_html_to_conversation(event.conv_id, "<i>you must have a 1on1 with the bot first</i>")
    else:
        parameters.remove(_externals["authorisation"])
        _externals["authorisation"] = False

        list_remove = []
        list_add = []

        state = ["adduser"]

        for parameter in parameters:
            if parameter == "without":
                state.append("removeuser")
            elif parameter == "add":
                state.append("adduser")
            else:
                if state[-1] == "adduser":
                    list_add.append(parameter)
                    if parameter in list_remove:
                        list_remove.remove(parameter)

                elif state[-1] == "removeuser":
                    list_remove.append(parameter)
                    if parameter in list_add:
                        list_add.remove(parameter)

                else:
                    raise ValueError("UNKNOWN STATE: {}".format(state[-1]))

        list_remove = list(set(list_remove))
        list_add = list(set(list_add))

        for u in sorted(event.conv.users, key=lambda x: x.full_name.split()[-1]):
            if not u.id_.chat_id in user_ids_to_remove:
                list_add.append(u.id_.chat_id)

        response = yield from bot._client.createconversation(list_add)

        new_conversation_id = response['conversation']['id']['id']
        bot.send_html_to_conversation(new_conversation_id, _("<i>new conversation created</i><br /><b>leave the old one</b>"))
        bot.send_html_to_conversation(event.conv_id, _("<b>PLEASE LEAVE THIS HANGOUT</b>"))
