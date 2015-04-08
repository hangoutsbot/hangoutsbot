import asyncio
import hangups
import time

from hangups.ui.utils import get_conv_name

class __internal_vars():
    def __init__(self):
        self.last_verified = {}


_internal = __internal_vars()


def _initialise(Handlers, bot=None):
    Handlers.register_handler(_check_if_admin_added_me, type="membership")
    Handlers.register_handler(_verify_botkeeper_presence, type="message")

    if "register_admin_command" in dir(Handlers) and "register_user_command" in dir(Handlers):
        Handlers.register_admin_command(["allowbotadd", "removebotadd"])
        return []
    else:
        print(_("RESTRICTEDADD: LEGACY FRAMEWORK MODE"))
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
                print(_("RESTRICTEDADD: admin added me to {}").format(
                    event.conv_id))
            elif initiator_user_id in allowbotadd:
                # bot added by an authorised user: /bot allowbotadd <id>
                print(_("RESTRICTEDADD: authorised user added me to {}").format(
                    event.conv_id))
            else:
                print(_("RESTRICTEDADD: user {} tried to add me to {}").format(
                    event.user.full_name,
                    event.conv_id))

                bot.send_message_parsed(
                    event.conv,
                    _("<i>{}, you need to be authorised to add me to another conversation. I'm leaving now...</i>").format(event.user.full_name))

                yield from _leave_the_chat_quietly(bot, event, command)


@asyncio.coroutine
def _verify_botkeeper_presence(bot, event, command):
    if not bot.get_config_option('strict_botkeeper_check'):
        return

    try:
        if time.time() - _internal.last_verified[event.conv_id] < 60:
            # don't check on every event
            return
    except KeyError:
        # not set - first time, so do a check
        pass

    if len(event.conv.users) < 3:
        # groups only!
        return

    admins_list = bot.get_config_suboption(event.conv_id, 'admins')
    if bot.memory.exists(["allowbotadd"]):
        allowbotadd = bot.memory.get("allowbotadd")
    else:
        allowbotadd = []

    botkeeper = False
    for user in event.conv.users:
        if user.id_.chat_id in admins_list or user.id_.chat_id in allowbotadd:
            # at least one user is a botkeeper
            print(_("RESTRICTEDADD: found botkeeper {}").format(user.id_.chat_id))
            botkeeper = True
            break

    _internal.last_verified[event.conv_id] = time.time()

    if not botkeeper:
        print(_("RESTRICTEDADD: no botkeeper in {}").format(
            event.conv_id))

        bot.send_message_parsed(
            event.conv,
            _("<i>There is no botkeeper in here. I have to go...</i>"))

        yield from _leave_the_chat_quietly(bot, event, command)


@asyncio.coroutine
def _leave_the_chat_quietly(bot, event, command):
    yield from asyncio.sleep(1.0)
    yield from command.run(bot, event, *["leave", "quietly"])


def allowbotadd(bot, event, user_id, *args):
    """add supplied user id as a botkeeper.
    botkeepers are allowed to add bots into a conversation and their continued presence in a
    conversation keeps the bot from leaving.
    """

    if not bot.memory.exists(["allowbotadd"]):
        bot.memory["allowbotadd"] = []

    allowbotadd = bot.memory.get("allowbotadd")
    allowbotadd.append(user_id)
    bot.send_message_parsed(
        event.conv,
        _("user id {} added as botkeeper").format(user_id))
    bot.memory["allowbotadd"] = allowbotadd
    bot.memory.save()

    _internal.last_verified = {} # force checks everywhere


def removebotadd(bot, event, user_id, *args):
    """remove supplied user id as a botkeeper.
    botkeepers are allowed to add bots into a conversation and their continued presence in a
    conversation keeps the bot from leaving. warning: removing a botkeeper may cause the bot to
    leave conversations where the current botkeeper is present, if no other botkeepers are present.
    """

    if not bot.memory.exists(["allowbotadd"]):
        bot.memory["allowbotadd"] = []

    allowbotadd = bot.memory.get("allowbotadd")
    if user_id in allowbotadd:
        allowbotadd.remove(user_id)
        bot.send_message_parsed(
            event.conv,
            _("user id {} removed as botkeeper").format(user_id))

        bot.memory["allowbotadd"] = allowbotadd
        bot.memory.save()

        _internal.last_verified = {} # force checks everywhere
    else:
        bot.send_message_parsed(
            event.conv,
            _("user id {} is not authorised").format(user_id))
