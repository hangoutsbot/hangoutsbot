import asyncio, logging, time

import hangups

import plugins


logger = logging.getLogger(__name__)


class __internal_vars():
    def __init__(self):
        self.last_verified = {}


_internal = __internal_vars()


def _initialise(bot):
    plugins.register_handler(_check_if_admin_added_me, type="membership")
    plugins.register_handler(_verify_botkeeper_presence, type="message")
    plugins.register_admin_command(["allowbotadd", "removebotadd"])


def _botkeeper_list(bot, conv_id):
    botkeepers = []

    # users can be tagged as botkeeper
    tagged_botkeeper = list(bot.tags.userlist(conv_id, "botkeeper").keys())

    # config.admins are always botkeepers
    admins_list = bot.get_config_suboption(conv_id, 'admins')
    if not admins_list:
        admins_list = []

    # legacy: memory.allowbotadd are explicitly defined as botkeepers
    if bot.memory.exists(["allowbotadd"]):
        allowbotadd = bot.memory.get("allowbotadd")
    else:
        allowbotadd = []

    botkeepers = tagged_botkeeper + admins_list + allowbotadd

    botkeepers = list(set(botkeepers) - set([ bot.user_self()["chat_id"] ]))

    return botkeepers


@asyncio.coroutine
def _check_if_admin_added_me(bot, event, command):
    bot_id = bot._user_list._self_user.id_
    if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        if bot_id in event.conv_event.participant_ids:
            # bot was part of the event
            initiator_user_id = event.user_id.chat_id

            if initiator_user_id in _botkeeper_list(bot, event.conv_id):
                logger.info("botkeeper added me to {}".format(event.conv_id))

            elif initiator_user_id == bot.user_self()["chat_id"]:
                logger.info("bot added self to {}".format(event.conv_id))

            elif event.conv_id in bot.conversations.get("tag:restrictedadd-whitelist"):
                logger.info("bot added to whitelisted {}".format(event.conv_id))

            else:
                logger.warning("{} ({}) tried to add me to {}".format(
                    initiator_user_id, event.user.full_name, event.conv_id))

                yield from bot.coro_send_message(
                    event.conv,
                    _("<i>{}, you need to be authorised to add me to another conversation. I'm leaving now...</i>").format(event.user.full_name))

                yield from _leave_the_chat_quietly(bot, event, command)


@asyncio.coroutine
def _verify_botkeeper_presence(bot, event, command):
    if not bot.get_config_suboption(event.conv_id, 'strict_botkeeper_check'):
        return

    if event.conv_id in bot.conversations.get("tag:restrictedadd-whitelist"):
        return

    try:
        if bot.conversations.catalog[event.conv_id]["type"] != "GROUP":
            return
    except KeyError:
        logger.warning("{} not found in permanent memory, skipping temporarily")
        return

    try:
        if time.time() - _internal.last_verified[event.conv_id] < 60:
            # don't check on every event
            return
    except KeyError:
        # not set - first time, so do a check
        pass

    botkeeper = False

    botkeeper_list = _botkeeper_list(bot, event.conv_id)

    for user in event.conv.users:
        if user.id_.chat_id in botkeeper_list:
            logger.debug("botkeeper found for {}: {}".format(event.conv_id, user.id_.chat_id))
            botkeeper = True
            break

    _internal.last_verified[event.conv_id] = time.time()

    if not botkeeper:
        logger.warning("no botkeeper in {}".format(event.conv_id))

        yield from bot.coro_send_message(
            event.conv,
            _("<i>There is no botkeeper in here. I have to go...</i>"))

        yield from _leave_the_chat_quietly(bot, event, command)


@asyncio.coroutine
def _leave_the_chat_quietly(bot, event, command):
    yield from asyncio.sleep(10.0)
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
    yield from bot.coro_send_message(
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
        yield from bot.coro_send_message(
            event.conv,
            _("user id {} removed as botkeeper").format(user_id))

        bot.memory["allowbotadd"] = allowbotadd
        bot.memory.save()

        _internal.last_verified = {} # force checks everywhere
    else:
        yield from bot.coro_send_message(
            event.conv,
            _("user id {} is not authorised").format(user_id))
