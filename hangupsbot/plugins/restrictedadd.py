import asyncio
import hangups

from hangups.ui.utils import get_conv_name

def _initialise(Handlers, bot=None):
    Handlers.register_handler(_check_if_admin_added_me, type="membership")
    return ["allowbotadd", "removebotadd"]

@asyncio.coroutine
def _check_if_admin_added_me(bot, event, command):
    bot_id = bot._user_list._self_user.id_
    if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        if bot_id in event.conv_event.participant_ids:
            # bot was part of the event
            initiator_user_id = event.user_id.chat_id
            admins_list = bot.get_config_suboption(event.conv_id, 'admins')
            if bot.memory.exists(["allowbotadd"]):
                allowbotadd = bot.memory.get("allowbotadd")
            else:
                allowbotadd = []

            if initiator_user_id in admins_list:
                # bot added by an admin
                print("RESTRICTEDADD: admin added me to {}".format(
                    event.conv_id))
            elif initiator_user_id in allowbotadd:
                # bot added by an admin
                print("RESTRICTEDADD: authorised user added me to {}".format(
                    event.conv_id))
            else:
                print("RESTRICTEDADD: user {} tried to add me to {}".format(
                    event.user.full_name, 
                    event.conv_id))

                bot.send_message_parsed(
                    event.conv, 
                    "<i>{}, you need to be authorised to add me to another conversation. I'm leaving now...</i>".format(event.user.full_name))

                yield from asyncio.sleep(1.0)
                yield from command.run(bot, event, *["leave", "quietly"])

def allowbotadd(bot, event, user_id, *args):
    if not bot.memory.exists(["allowbotadd"]):
        bot.memory["allowbotadd"] = []

    allowbotadd = bot.memory.get("allowbotadd")
    allowbotadd.append(user_id)
    bot.send_message_parsed(
        event.conv,
        "user id {} authorised to add bot in any conversations".format(user_id))

    bot.memory["allowbotadd"] = allowbotadd
    bot.memory.save()

def removebotadd(bot, event, user_id, *args):
    if not bot.memory.exists(["allowbotadd"]):
        bot.memory["allowbotadd"] = []

    allowbotadd = bot.memory.get("allowbotadd")
    if user_id in allowbotadd:
        allowbotadd.remove(user_id)
        bot.send_message_parsed(
            event.conv,
            "user id {} authorisation to add bot in any conversations removed".format(user_id))

        bot.memory["allowbotadd"] = allowbotadd
        bot.memory.save()
    else:
        bot.send_message_parsed(
            event.conv,
            "user id {} is not authorised".format(user_id))