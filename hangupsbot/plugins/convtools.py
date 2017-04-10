# Original Author of addme/add/addfrom/compare/hoalias: kilr00y@esthar.net

import asyncio, logging, random, string

import hangups

import plugins

from commands import command

import functools

logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_admin_command(["addme", "addusers", "createconversation", "refresh", "kick", "sethoalias", "gethoalias", "removehoalias", "add", "addfrom", "compare"])
    plugins.register_shared("hoalias.list",functools.partial(get_hoaliaslist, bot))
    return []

def get_hoaliaslist(bot):
    if not bot.memory.exists(["hoalias"]):
        bot.memory["hoalias"] = {}
    return bot.memory["hoalias"]

@asyncio.coroutine
def removehoalias(bot, event, *args):
    """Remove a HO alias<br>
    <b>Usage:</b> /bot removehoalias <hoalias>"""
    if len(args) != 1:
        yield from bot.coro_send_message(event.conv, "<b>ERROR!</b><br><b>Usage:</b> /bot removehoalias <hoalias>")
    else:
        alias_list = get_hoaliaslist(bot)
        alias = args[0]
        if bot.memory.exists(["hoalias",alias]):
            alias_list.pop(alias)
            bot.memory.save()
            yield from bot.coro_send_message(event.conv, "Alias for <b>{}</b> deleted".format(alias))
        else:
            yield from bot.coro_send_message(event.conv, "There is no alias for <b>{}</b>".format(alias))

@asyncio.coroutine
def sethoalias(bot, event, *args):
    """Set a HO alias<br>
    <b>Usage:</b><br> /bot sethoalias <hoalias> (for current HO)<br>/bot sethoalias none (to clear current HO alias)<br>/bot sethoalias <hoalias> <convID> (for another HO)<br>/bot sethoalias none <convid> (to clear HO alias for another HO)"""
    if len(args) < 1 or len(args) > 2 or (len(args) == 2 and len(args[1]) != 26):
        yield from bot.coro_send_message(event.conv, "<b>ERROR!</b><br><b>Usage:</b><br> /bot sethoalias <hoalias> (for current HO)<br>/bot sethoalias none (to clear current HO alias)<br>/bot sethoalias <hoalias> <convID> (for another HO)<br>/bot sethoalias none <convid> (to clear HO alias for another HO)")
    else:
        alias_list = get_hoaliaslist(bot)
        newalias = args[0]
        if len(args)==1:
            convID = event.conv_id
        else:
            convID = args[1]
        oldalias = None
        for _alias,_id in alias_list.items():
            if _id == event.conv_id:
                oldalias = _alias
                                        
        if bot.memory.exists(["hoalias",newalias]) and newalias.lower() != "none":
            alias_list.pop(newalias)
        if bot.memory.exists(["hoalias",oldalias]):
            alias_list.pop(oldalias)
        if newalias.lower() != "none":
            alias_list[newalias]=convID
        bot.memory.force_taint()
        bot.memory.save()

        if newalias == "none" and len(args)==1:
            yield from bot.coro_send_message(event.conv, "HO alias deleted")
        elif newalias == "none" and len(args)==2:
            yield from bot.coro_send_message(event.conv, "HO alias for <b>{}</b> deleted".format(convID))
        elif len(args)==1:
            yield from bot.coro_send_message(event.conv, "HO alias set to <b>{}</b>".format(newalias))
        else:
            yield from bot.coro_send_message(event.conv, "HO alias for <b>{}</b> is set to <b>{}</b>".format(convID,newalias))

@asyncio.coroutine
def gethoalias(bot, event, *args):
    """Get list of HO aliases<br>
    <b>Usage:</b><br> /bot gethoalias (for current HO) <br> /bot gethoalias all (for all HOs)"""
    if len(args) > 1:
        yield from bot.coro_send_message(event.conv, "<b>ERROR!</b><br><b>Usage:</b><br> /bot gethoalias (for current HO)<br>/bot gethoalias all (for all HOs)")
    else:
        alias_list = get_hoaliaslist(bot)
        if len(args)==1 and args[0].lower() == "all":
            text="<u>List of HO Aliases</u><br />"
            for _alias,_id in alias_list.items():
                text+="<b>"+_alias+"</b> <i>("+_id+")</i><br />"
            yield from bot.coro_send_message(event.conv,text)
        else:    
            if len(args)==1:
                convID=args[0]
            else:
                convID=event.conv_id
            alias = None
            for _alias,_id in alias_list.items():
                if _id == convID:
                    alias = _alias
            if alias == None:
                yield from bot.coro_send_message(event.conv, "There is no alias set for this HO.")
            elif len(args) == 1:
                yield from bot.coro_send_message(event.conv, "HO alias for <b>{}</b> is <b>{}</b>".format(convID,alias))
            else:
                yield from bot.coro_send_message(event.conv, "Current HO alias is <b>{}</b>".format(alias))


                
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
        logger.info("Batch add users: {}/{} {} user(s) into {}".format(number+1, len(chunks), len(partial_list), target_conv))

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

@asyncio.coroutine
def add(bot, event, *args):
    """Add users to hangout<br>
    <b>Usage:</b> /bot add <hoalias> <userChatID>
	<b>Note:</b> must have set hoalias, use <b>/bot gethoalias all</b> for full list"""
    if len(args)<2:
        yield from bot.coro_send_message(event.conv,"<b>ERROR!</b><br><b>Usage:</b><br> /bot add <hoalias> <userChatID>")
    else:
        destinations=[]
        users=[]
        alias_list = bot.call_shared("hoalias.list")
        for arg in args:
            if arg.isdigit():
                users.append(arg)
            else:
                try: 
                    _id=alias_list[arg]
                except:
                    yield from bot.coro_send_message(event.conv,"<b>ADDUSERS:</b> <i>HO alias</i> <b>{}</b> <i>does not exist</i>".format(arg))
                else:
                    destinations.append(arg)
                
        if len(users)<1 or len(destinations)<1:
            yield from bot.coro_send_message(event.conv,"<b>ADDUSERS:</b> <i>you need to supply at least one user and one valid HOalias</i>")
        else:
            yield from bot.coro_send_message(event.conv,"<b>ADDUSERS:</b> <i>trying to add {} users to {} Hangouts</i>".format(len(users),len(destinations)))
            for destination in destinations:
                _destination=alias_list[destination]
                for _user in users:
                    __user=[]
                    __user.append(_user)
                    yield from asyncio.sleep(1)
                    try:
                        yield from bot._client.add_user(
                            hangups.hangouts_pb2.AddUserRequest(
                                request_header = bot._client.get_request_header(),
                                invitee_id = [ hangups.hangouts_pb2.InviteeID(gaia_id = _user) ],
                                event_request_header = hangups.hangouts_pb2.EventRequestHeader(
                                    conversation_id = hangups.hangouts_pb2.ConversationId(id = _destination),
                                    client_generated_id = bot._client.get_client_generated_id() )))
                    except:
                        text="<b>ADDUSERS:</b> adding "
                        user_object = bot.get_hangups_user(_user)
                        fullname = user_object.full_name
                        text+="{}".format(fullname)
                        text+=" to <b>{}</b>....<b>FAILED</b>.".format(destination)
                        yield from bot.coro_send_message(event.conv,text)
                    else:
                        text="<b>ADDUSERS:</b> adding "
                        user_object = bot.get_hangups_user(_user)
                        fullname = user_object.full_name
                        text+="{}".format(fullname)
                        text+=" to <b>{}</b>....<b>SUCCESSFUL</b>.".format(destination)
                        yield from bot.coro_send_message(event.conv,text)

@asyncio.coroutine
def compare(bot, event, *args):
    """Compare users from one chat to another<br>
    <b>Usage:</b> 
	/bot compare diff <hangout1> <hangout2> for difference
	/bot compare common <hangout1> <hangout2> for common users	
	<b>Note:</b> must have set hoalias, use <b>/bot gethoalias all</b> for full list"""
    if len(args)!=3 or (len(args)==3 and not args[0] in ["common","diff"]):
        yield from bot.coro_send_message(event.conv,"<b>ERROR!</b><br><b>Usage:</b><br> /bot compare diff <hangout1> <hangout2><br>/bot compare common <hangout1> <hangout2>")
    else:
        mode=args[0]
        alias1=args[1]
        alias2=args[2]
        alias_list = bot.call_shared("hoalias.list")
        
        try:
            hangout1=alias_list[alias1]
        except:
            yield from bot.coro_send_message(event.conv,"HO alias <b>{}</b> does not exist".format(alias1))
            return
        
        try:
            hangout2=alias_list[alias2]
        except:
            yield from bot.coro_send_message(event.conv,"HO alias <b>{}</b> does not exist".format(alias2))
            return
        
        hangout1_users=bot.get_users_in_conversation(hangout1)
        hangout2_users=bot.get_users_in_conversation(hangout2)
        users=[]
        
        if mode=="common":
            for _user in hangout1_users:
                if _user in hangout2_users:
                    users.append(_user.id_.chat_id)
            if len(users)==0:
                text="There are no users that are in <b>{}</b> as well as in <b>{}</b>".format(alias1,alias2)
            else:
                text="These {} users are in <b>{}</b> as well as in <b>{}</b><br /><br />".format(len(users),alias1,alias2)
        elif mode=="diff":
            for _user in hangout1_users:
                if not _user in hangout2_users:
                    users.append(_user.id_.chat_id)
            if len(users)==0:
                text="All users that are in <b>{}</b> are also in <b>{}</b>".format(alias1,alias2)
            else:
                text="These {} users are in <b>{}</b>, but not in <b>{}</b><br /><br />".format(len(users),alias1,alias2)
        
        if users:
            for _user in users:
                user_object = bot.get_hangups_user(_user)
                fullname=user_object.full_name
                text+="{} <br />".format(fullname)
                        

        yield from bot.coro_send_message(event.conv,text)

                    
@asyncio.coroutine
def addfrom(bot, event, *args):
    """Add users from one chat to another<br>
    <b>Usage:</b> /bot addfrom <sourcehangout> <destinationhangout>
	<b>Note:</b> must have set hoalias, use <b>/bot gethoalias all</b> for full list"""
    if len(args)!=2:
        yield from bot.coro_send_message(event.conv,"<b>ERROR!</b><br><b>Usage:</b> /bot addfrom <sourcehangout> <destinationhangout>")
    else:
        sourcealias=args[0]
        destinationalias=args[1]
        alias_list = bot.call_shared("hoalias.list")
        
        try:
            source=alias_list[sourcealias]
        except:
            yield from bot.coro_send_message(event.conv,"HO alias <b>{}</b> does not exist".format(sourcealias))
            return

        try:
            destination=alias_list[destinationalias]
        except:
            yield from bot.coro_send_message(event.conv,"HO alias <b>{}</b> does not exist".format(destinationalias))
            return
                                            
        source_users=bot.get_users_in_conversation(source)
        dest_users=bot.get_users_in_conversation(destination)
        add_users=[]
        user_succ=0
        
        for _user in source_users:
            if not _user in dest_users:
                add_users.append(_user.id_.chat_id)
                
        if not add_users:
            yield from bot.coro_send_message(event.conv,"<b>ADDFROM:</b> All the users in <b>{}</b> are already in <b>{}</b>".format(sourcealias,destinationalias))
        else:
            yield from bot.coro_send_message(event.conv,"<b>ADDFROM:</b> Trying to add {} users from <b>{}</b> to <b>{}</b>".format(len(add_users),sourcealias,destinationalias))
            yield from asyncio.sleep(1)
            try:
                for _user in add_users:
                    __user=[]
                    __user.append(_user)
                    yield from bot._client.add_user(
                        hangups.hangouts_pb2.AddUserRequest(
                            request_header = bot._client.get_request_header(),
                            invitee_id = [ hangups.hangouts_pb2.InviteeID(gaia_id = _user) ],
                            event_request_header = hangups.hangouts_pb2.EventRequestHeader(
                                conversation_id = hangups.hangouts_pb2.ConversationId(id = destination),
                                client_generated_id = bot._client.get_client_generated_id() )))
            except:
                text="<b>ADDFROM:</b> failed to add user "
                user_object = bot.get_hangups_user(_user)
                fullname = user_object.full_name
                text+="<b>{}<b>".format(fullname)
                yield from bot.coro_send_message(event.conv,text)
            else:
                text="<b>ADDFROM:</b> Suceeded for "
                user_succ = len(add_users)
                text+="{}".format(user_succ)
                text+=" users."
                yield from bot.coro_send_message(event.conv,text)	

@asyncio.coroutine
def addme(bot, event, *args):
    """Add yourself into a chat<br>
    <b>Usage:</b> /bot addme <hoalias>
	<b>Note:</b> must have set hoalias, use <b>/bot gethoalias all</b> for full list"""
    if len(args) != 1:
        yield from bot.coro_send_message(event.conv, "<b>ERROR!</b><br><b>Usage:</b> /bot addme <hoalias>")
    else:
        bot.memory.exists(['user_data', event.user_id.chat_id])
        alias=args[0]
        alias_list = bot.call_shared("hoalias.list")
        user_id = event.user.id_.chat_id
        try:
            group_id = alias_list[alias]
        except:
            yield from bot.coro_send_message(event.conv,"<b>{}</b> is unknown".format(alias))
            return
        try:
            yield from bot._client.add_user(
                hangups.hangouts_pb2.AddUserRequest(
                    request_header = bot._client.get_request_header(),
                    invitee_id = [ hangups.hangouts_pb2.InviteeID(gaia_id = user_id) ],
                    event_request_header = hangups.hangouts_pb2.EventRequestHeader(
                        conversation_id = hangups.hangouts_pb2.ConversationId(id = group_id),
                        client_generated_id = bot._client.get_client_generated_id() )))            
        except:
            yield from bot.coro_send_message(event.conv,"Adding you to <b>{}</b> failed".format(alias))
        else:
            yield from bot.coro_send_message(event.conv,"You were added to <b>{}</b>".format(alias))	


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
