import asyncio, logging, random, string

import hangups

import plugins

from commands import command


logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_admin_command(["addme", "addusers", "createconversation", "refresh", "kick"])


@asyncio.coroutine
def _batch_add_users(bot, target_conv, chat_ids, batch_max=20):
    chat_ids = list(set(chat_ids))

    not_there = []
    for chat_id in chat_ids:
        if chat_id not in bot.conversations.catalog[target_conv]["participants"]:
            not_there.append(chat_id)
        else:
            logger.debug("addusers: user {} already in {}".format(chat_id, target_conv))
    chat_ids = not_there

    users_added = 0
    chunks = [chat_ids[i:i+batch_max] for i in range(0, len(chat_ids), batch_max)]
    for number, partial_list in enumerate(chunks):
        logger.info("batch add users: {}/{} {} user(s) into {}".format(number+1, len(chunks), len(partial_list), target_conv))

        yield from bot._client.add_user(
            hangups.hangouts_pb2.AddUserRequest(
                request_header = bot._client.get_request_header(),
                invitee_id = [ hangups.hangouts_pb2.InviteeID(gaia_id = chat_id)
                               for chat_id in partial_list ],
                event_request_header = hangups.hangouts_pb2.EventRequestHeader(
                    conversation_id = hangups.hangouts_pb2.ConversationId(id = target_conv),
                    client_generated_id = bot._client.get_client_generated_id() )))

        users_added = users_added + len(partial_list)
        yield from asyncio.sleep(0.5)

    return users_added


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
    added = 0
    if len(list_add) > 0:
        added = yield from _batch_add_users(bot, target_conv, list_add)
    logger.info("addusers: {} added to {}".format(added, target_conv))


def addme(bot, event, *args):
    """add yourself into a chat
    Usage: /bot addme <conv id>"""
    if len(args) == 1:
        target_conv = args[0]
        yield from addusers(bot, event, *[event.user.id_.chat_id, "into", target_conv])

    else:
        raise ValueError(_("supply the id of the conversation to join"))


def createconversation(bot, event, *args):
    """create a new conversation with the bot and the specified user(s)
    Usage: /bot createconversation <user id(s)>"""
    parameters = list(args)

    force_group = True # only create groups

    if "group" in parameters:
        # block maintained for legacy command support
        # removes redundant supplied parameter
        parameters.remove("group")
        force_group = True

    user_ids = list(set(parameters))
    logger.info("createconversation: {}".format(user_ids))

    _response = yield from bot._client.create_conversation(
        hangups.hangouts_pb2.CreateConversationRequest(
            request_header = bot._client.get_request_header(),
            type = hangups.hangouts_pb2.CONVERSATION_TYPE_GROUP,
            client_generated_id = bot._client.get_client_generated_id(),
            invitee_id = [ hangups.hangouts_pb2.InviteeID(gaia_id = chat_id)
                           for chat_id in user_ids ]))
    new_conversation_id = _response.conversation.conversation_id.id

    yield from bot.coro_send_message(new_conversation_id, "<i>conversation created</i>")


def refresh(bot, event, *args):
    """refresh a chat
    Usage: /bot refresh
    [conversation] <conversation id>
    [without|remove <user ids, space-separated if more than one>]
    [with|add <user id(s)>]
    [quietly]
    [norename]"""
    parameters = list(args)

    test = False
    quietly = False
    source_conv = False
    renameold = True
    list_removed = []
    list_added = []

    state = ["conversation"]

    for parameter in parameters:
        if parameter == "remove" or parameter == "without":
            state.append("removeuser")
        elif parameter == "add" or parameter == "with":
            state.append("adduser")
        elif parameter == "conversation":
            state.append("conversation")
        elif parameter == "quietly":
            quietly = True
            renameold = False
        elif parameter == "test":
            test = True
        elif parameter == "norename":
            renameold = False
        else:
            if state[-1] == "adduser":
                list_added.append(parameter)
                if parameter in list_removed:
                    list_removed.remove(parameter)

            elif state[-1] == "removeuser":
                list_removed.append(parameter)
                if parameter in list_added:
                    list_added.remove(parameter)

            elif state[-1] == "conversation":
                source_conv = parameter

            else:
                raise ValueError("UNKNOWN STATE: {}".format(state[-1]))

    list_removed = list(set(list_removed))

    if not source_conv:
        raise ValueError("conversation id not supplied")

    if source_conv not in bot.conversations.catalog:
        raise ValueError(_("conversation {} not found").format(source_conv))

    if bot.conversations.catalog[source_conv]["type"] != "GROUP":
        raise ValueError(_("conversation {} is not a GROUP").format(source_conv))

    new_title = bot.conversations.get_name(source_conv)
    old_title = _("[DEFUNCT] {}".format(new_title))

    text_removed_users = []
    list_all_users = bot.get_users_in_conversation(source_conv)
    for u in list_all_users:
        if u.id_.chat_id not in list_removed:
            list_added.append(u.id_.chat_id)
        else:
            hangups_user = bot.get_hangups_user(u.id_.chat_id)
            text_removed_users.append("<pre>{}</pre> ({})".format(hangups_user.full_name, u.id_.chat_id))

    list_added = list(set(list_added))

    logger.debug("refresh: from conversation {} removed {} added {}".format(source_conv, len(list_removed), len(list_added)))

    if test:
        yield from bot.coro_send_message(event.conv_id,
                                         _("<b>refresh:</b> {}<br />"
                                           "<b>rename old: {}</b><br />"
                                           "<b>removed {}:</b> {}<br />"
                                           "<b>added {}:</b> {}").format(source_conv,
                                                                         old_title if renameold else _("<em>unchanged</em>"),
                                                                         len(text_removed_users),
                                                                         ", ".join(text_removed_users) or _("<em>none</em>"),
                                                                         len(list_added),
                                                                         " ".join(list_added) or _("<em>none</em>")))
    else:
        if len(list_added) > 1:

            _response = yield from bot._client.create_conversation(
                hangups.hangouts_pb2.CreateConversationRequest(
                    request_header = bot._client.get_request_header(),
                    type = hangups.hangouts_pb2.CONVERSATION_TYPE_GROUP,
                    client_generated_id = bot._client.get_client_generated_id(),
                    invitee_id = []))
            new_conversation_id = _response.conversation.conversation_id.id

            yield from bot.coro_send_message(new_conversation_id, _("<i>refreshing group...</i><br />"))
            yield from asyncio.sleep(1)
            yield from _batch_add_users(bot, new_conversation_id, list_added)
            yield from bot.coro_send_message(new_conversation_id, _("<i>all users added</i><br />"))
            yield from asyncio.sleep(1)
            yield from command.run(bot, event, *["convrename", "id:" + new_conversation_id, new_title])

            if renameold:
                yield from command.run(bot, event, *["convrename", "id:" + source_conv, old_title])

            if not quietly:
                yield from bot.coro_send_message(source_conv, _("<i>group has been obsoleted</i>"))

            yield from bot.coro_send_message( event.conv_id,
                                              _("refreshed: <b><pre>{}</pre></b> (original id: <pre>{}</pre>).<br />"
                                                "new conversation id: <b><pre>{}</pre></b>.<br />"
                                                "removed {}: {}").format( new_title,
                                                                          source_conv,
                                                                          new_conversation_id,
                                                                          len(text_removed_users),
                                                                          ", ".join(text_removed_users) or _("<em>none</em>") ))

        else:
            yield from bot.coro_send_message(event.conv_id, _("<b>nobody to add in the new conversation</b>"))


def kick(bot, event, *args):
    """kick users from a conversation
    Usage: /bot kick
    [<optional conversation id, current if not specified>]
    [<user ids, space-separated if more than one>]
    [quietly]"""
    parameters = list(args)

    source_conv = event.conv_id
    remove = []
    test = False
    quietly = False

    for parameter in parameters:
        if parameter in bot.conversations.catalog:
            source_conv = parameter
        elif parameter in bot.conversations.catalog[source_conv]["participants"]:
            remove.append(parameter)
        elif parameter == "test":
            test = True
        elif parameter == "quietly":
            quietly = True
        else:
            raise ValueError(_("supply optional conversation id and valid user ids to kick"))

    if len(remove) <= 0:
        raise ValueError(_("supply at least one valid user id to kick"))

    arguments = ["refresh", source_conv, "without"] + remove

    if test:
        arguments.append("test")

    if quietly:
        arguments.append("quietly")

    yield from command.run(bot, event, *arguments)
