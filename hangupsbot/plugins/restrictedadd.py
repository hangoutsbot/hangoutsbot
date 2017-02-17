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
    plugins.register_admin_command(["allowbotadd", "removebotadd", "botaddnotify"])

    if not bot.get_config_option('botkeeper_check_notify'):
        bot.config.set_by_path(['botkeeper_check_notify'], False)
        bot.config.save()
        return

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

            #If initiator_user_id != bot_id (i.e the bot account didn't join via link)
            #If it did join via link _verfiy_botkeeper_presence() will catch it.
            if initiator_user_id != bot.user_self()["chat_id"]:

                # check if botkeeper added
                if initiator_user_id in _botkeeper_list(bot, event.conv_id):
                    logger.info("botkeeper added me to {}".format(event.conv_id))

                else:
                    logger.warning("{} ({}) tried to add me to {}".format(
                        initiator_user_id, event.user.full_name, event.conv_id))

                    notify = bot.config.get_option('botkeeper_check_notify')

                    if notify is True:
                        yield from bot.coro_send_to_user_and_conversation(
                            _botkeeper_list(bot, event.conv_id)[0], event.conv_id,
                            _("<b>{}</b> ({}) tried to add me to<br/><b>{}</b><br />Run this command to enable me to stay next time:".format(event.user.full_name, initiator_user_id, bot.conversations.get_name(event.conv_id,fallback_string="? {}".format(event.conv_id)))), 
                            _("<i>{}, you need to be authorised to add me to another conversation. I'm leaving now...</i>").format(event.user.full_name))

                        yield from bot.coro_send_to_user(_botkeeper_list(bot, event.conv_id)[0], ("{} botaddnotify {}").format(bot._handlers.bot_command[0],event.conv_id))

                    else:
                        yield from bot.coro_send_message(
                            event.conv,
                            _("<i>{}, you need to be authorised to add me to another conversation. I'm leaving now...</i>").format(event.user.full_name))

                    yield from _leave_the_chat_quietly(bot, event, command)


@asyncio.coroutine
def _verify_botkeeper_presence(bot, event, command):
    if not bot.get_config_suboption(event.conv_id, 'strict_botkeeper_check'):
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

        notify = bot.config.get_option('botkeeper_check_notify')
        if notify is True:
            yield from bot.coro_send_to_user_and_conversation(
                _botkeeper_list(bot, event.conv_id)[0], event.conv_id,
                _("I was in this hangout without a keeper<br/><b>{}</b><br />Run this command to enable me to stay next time:".format(bot.conversations.get_name(event.conv_id,fallback_string="? {}".format(event.conv_id)))), 
                _("<i>I can't be in here without a chaperone.<br />I'm leaving now...</i>"))

            yield from bot.coro_send_to_user(_botkeeper_list(bot, event.conv_id)[0], ("{} botaddnotify {}").format(bot._handlers.bot_command[0],event.conv_id))

        else:
            yield from bot.coro_send_message(
                event.conv,
                _("<i>I can't be in here without a chaperone.<br />I'm leaving now...</i>"))

        yield from _leave_the_chat_quietly(bot, event, command)


@asyncio.coroutine
def _leave_the_chat_quietly(bot, event, command):
    yield from asyncio.sleep(1.0)
    yield from command.run(bot, event, *["leave", "quietly"])


def allowbotadd(bot, event, user_id, *args):
    """<br />[botalias] <i><b>allowbotadd</b> <user_id></i><br />Add a user to the botkeeper list. The bot will remain in the hangout with them.<br /><u>Usage</u><br />[botalias] <i><b>allowbotadd</b> 110350977702120778591</i>"""

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
    """<br />[botalias] <i><b>removebotadd</b> <user_id></i><br />Remove a user from the botkeeper list.<br /><u>Usage</u><br />[botalias] <i><b>removebotadd</b> 110350977702120778591</i>"""

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



def botaddnotify(bot, event, conv_id):
    """<br />[botalias] <i><b>botaddnotify</b> <conv_id></i><br />Toggle whitelisting a conversation to avoid botkeeper checks.<br /><u>Usage</u><br />[botalias] <i><b>botaddnotify</b> AbcdefGHIjklmNOPQRStuVWXyz</i>"""
    
    if bot.config.exists(["conversations", convid, "strict_botkeeper_check"]):
        conv_settings = bot.config.get_by_path(['conversations', event.conv_id])
        del conv_settings['strict_botkeeper_check'] # remove setting

        bot.config.set_by_path(['conversations', event.conv_id], conv_settings)
        bot.config.save()

        yield from bot.coro_send_message(event.conv, ("<i>{}</i> is no longer whitelisted.").format(conv_id))

    else:
        if not bot.config.exists(['conversations']):
            bot.config.set_by_path(['conversations'],{})
        if not bot.config.exists(['conversations',conv_id]):
            bot.config.set_by_path(['conversations',conv_id],{})

        bot.config.set_by_path(['conversations', conv_id, 'strict_botkeeper_check'], False)
        bot.config.save()

        yield from bot.coro_send_message(event.conv, ("<i>{}</i> has been whitelisted.").format(conv_id))
