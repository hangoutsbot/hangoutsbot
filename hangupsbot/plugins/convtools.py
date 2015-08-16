import asyncio, logging, random, string

import plugins


logger = logging.getLogger(__name__)


_externals = { "authorisation": False }


def _initialise(bot):
    plugins.register_admin_command(["addme", "addusers", "createconversation", "refresh"])


def addusers(bot, event, *args):
    """adds user(s) into a chat
    Usage: /bot addusers
    <user id(s)>
    [into <chat id>]"""
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
                state.pop()
            else:
                raise ValueError("UNKNOWN STATE: {}".format(state[-1]))

    list_add = list(set(list_add))
    logger.info("addusers: {} into conversation {}".format(list_add, target_conv))
    if len(list_add) > 0:
        yield from bot._client.adduser(target_conv, list_add)


def addme(bot, event, *args):
    """add yourself into a chat
    Usage: /bot addme <conv id>"""
    if len(args) == 1:
        target_conv = args[0]
        yield from addusers(bot, event, *[event.user.id_.chat_id, "into", target_conv])


def createconversation(bot, event, *args):
    """create a new conversation with the bot and the specified user(s)
    Usage: /bot createconversation <user id(s)>"""
    parameters = list(args)

    force_group = False # default: defer to hangups client decision

    if "group" in parameters:
        parameters.remove("group")
        force_group = True

    user_ids = list(set(parameters))
    logger.info("createconversation: {}".format(user_ids))

    response = yield from bot._client.createconversation(user_ids, force_group)
    new_conversation_id = response['conversation']['id']['id']
    yield from bot.coro_send_message(new_conversation_id, "<i>conversation created</i>")


def refresh(bot, event, *args):
    """refresh a chat
    Usage: /bot refresh
    conversation <chat id>
    [without <user id(s)>]
    [add <user id(s)>] [quietly]"""
    parameters = list(args)

    if _externals["authorisation"] not in parameters:
        _externals["authorisation"] = False
        initiator_1on1 = yield from bot.get_1to1(event.user.id_.chat_id)
        if initiator_1on1:
            _externals["authorisation"] = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(8))
            yield from bot.coro_send_message(initiator_1on1, "<i>are you sure? execute the command again and append this key: {}</i>".format(_externals["authorisation"]))
        else:
            yield from bot.coro_send_message(event.conv_id, "<i>you must have a 1on1 with the bot first</i>")
    else:
        parameters.remove(_externals["authorisation"])
        _externals["authorisation"] = False

        quietly = False
        target_conv = False
        list_remove = []
        list_add = []

        state = ["adduser"]

        logger.info("refresh: {}".format(parameters))

        for parameter in parameters:
            if parameter == "without":
                state.append("removeuser")
            elif parameter == "add":
                state.append("adduser")
            elif parameter == "conversation":
                state.append("conversation")
            elif parameter == "quietly":
                quietly = True
            else:
                if state[-1] == "adduser":
                    list_add.append(parameter)
                    if parameter in list_remove:
                        list_remove.remove(parameter)

                elif state[-1] == "removeuser":
                    list_remove.append(parameter)
                    if parameter in list_add:
                        list_add.remove(parameter)

                elif state[-1] == "conversation":
                    target_conv = parameter
                    state.pop()

                else:
                    raise ValueError("UNKNOWN STATE: {}".format(state[-1]))

        list_remove = list(set(list_remove))

        if not target_conv:
            logger.error("REFRESH: conversation must be supplied")
            return

        list_all_users = bot.get_users_in_conversation(target_conv)
        logger.info("refresh: conversation {} has {} users".format(target_conv, len(list_all_users)))

        for u in list_all_users:
            if not u.id_.chat_id in list_remove:
                list_add.append(u.id_.chat_id)

        list_add = list(set(list_add))

        logger.info("refresh: from conversation {} removed {} added {} {}".format(target_conv, list_remove, len(list_add), list_add))

        if len(list_add) > 1:
            response = yield from bot._client.createconversation(list_add)

            new_conversation_id = response['conversation']['id']['id']
            yield from bot.coro_send_message(new_conversation_id, _("<i>group refreshed</i><br />"))
            yield from bot.coro_send_message(event.conv_id, _("<b>group obsoleted</b>"))
            if not quietly:
                yield from bot.coro_send_message(target_conv, _("<b>group obsoleted</b>"))
