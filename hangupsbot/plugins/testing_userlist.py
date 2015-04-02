import asyncio
from hangups.user import User

def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["refreshusers", "dumpusers"])
    return []

def refreshusers(bot, event, *args):
    for key in bot._user_list._user_dict:
        user_object = bot._user_list._user_dict[key]

        if user_object.first_name == "unknown":
            user_id = key.chat_id
            response = yield from bot._client.getentitybyid([user_id])
            print("{}".format(response))
            try:
                display_name = response['entity'][0]['properties']['display_name']
                first_name = response['entity'][0]['properties']['first_name']
                bot._user_list._user_dict[key] = User(key, display_name, first_name, None, [], False)
                print("refreshusers() {} {}".format(user_id, display_name))
            except Exception as e:
                print("refreshusers() {} {}".format(e, user_id))

def dumpusers(bot, event, *args):
    for key in bot._user_list._user_dict:
        user_object = bot._user_list._user_dict[key]
        if len(args) == 0 or " ".join(args) in user_object.full_name:
            print("{} {}".format(user_object.full_name, user_object.first_name))