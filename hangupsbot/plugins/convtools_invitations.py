import time, string, random, asyncio, logging, datetime

import hangups

import plugins

from commands import command


logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_admin_command(["invite"])
    plugins.register_user_command(["rsvp"])
    plugins.register_handler(_issue_invite_on_exit, type="membership")


def _remove_invite(bot, invite_code):
    memory_path = ["invites", invite_code]
    if bot.memory.exists(memory_path):
        popped_invitation = bot.memory.pop_by_path(memory_path)
        bot.memory.save()
        logger.debug("_remove_invite: {}".format(popped_invitation))
    else:
        logger.debug("_remove_invite: nothing removed")


def _issue_invite(bot, user_id, group_id, uses=1, expire_in=2592000, expiry=None):
    if not bot.memory.exists(["invites"]):
        bot.memory["invites"] = {}

    invitation = False

    # find existing unexpired invitation by user and group - exact match only
    for _key, _invitation in bot.memory["invites"].items():
        if _invitation["user_id"] == user_id and _invitation["group_id"] == group_id and _invitation["expiry"] > time.time():
            invitation = _invitation
            logger.debug("_issue_invite: found existing invite id: {}".format(invitation["id"]))
            break

    # create new invitation if no match found
    if not invitation:
        while True:
            _id = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6))
            if _id not in bot.memory["invites"]:
                logger.debug("_issue_invite: create new invite id: {}".format(_id))
                invitation = {
                    "id": _id,
                    "user_id": user_id,
                    "group_id": group_id
                }
                break

    if not invitation:
        raise ValueError("no invitation")

    # update/create some fields
    if not expiry:
        expiry = int(time.time()) + expire_in
    invitation["expiry"] = expiry
    invitation["uses"] = uses
    invitation["updated"] = time.time()

    # write to user memory
    bot.memory["invites"][invitation["id"]] = invitation
    bot.memory.force_taint()
    bot.memory.save()

    return invitation["id"]


@asyncio.coroutine
def _claim_invite(bot, invite_code, user_id):
    memory_path = ["invites", invite_code]

    if not bot.memory.exists(memory_path):
        return

    invitation = bot.memory.get_by_path(memory_path)
    if invitation["user_id"] in ("*", user_id) and invitation["expiry"] > time.time():

        try:
            logger.debug("_claim_invite: adding {} to {}".format(user_id, invitation["group_id"]))

            yield from bot._client.add_user(
                hangups.hangouts_pb2.AddUserRequest(
                    request_header = bot._client.get_request_header(),
                    invitee_id = [ hangups.hangouts_pb2.InviteeID(gaia_id = user_id) ],
                    event_request_header = hangups.hangouts_pb2.EventRequestHeader(
                        conversation_id = hangups.hangouts_pb2.ConversationId(id = invitation["group_id"]),
                        client_generated_id = bot._client.get_client_generated_id() )))

        except hangups.exceptions.NetworkError as e:
            # trying to add a user to a group where the user is already a member raises this
            logger.exception("_CLAIM_INVITE: FAILED {} {}".format(invite_code, user_id))
            return

        invitation["uses"] = invitation["uses"] - 1

        if invitation["uses"] > 0:
            bot.memory.set_by_path(memory_path, invitation)
            bot.memory.save()
        else:
            _remove_invite(bot, invite_code)

        logger.debug("_claim_invite: claimed {}".format(invitation))

    else:
        logger.debug("_claim_invite: invalid")


def _issue_invite_on_exit(bot, event, command):
    # Check if issue_invite_on_exit is disabled
    if bot.get_config_suboption(event.conv_id, 'disable_invites_on_exit'):
        return

    if event.conv_event.type_ == hangups.MembershipChangeType.LEAVE:
        event_users = [event.conv.get_user(user_id) for user_id
                       in event.conv_event.participant_ids]
        users_leaving = [user.id_.chat_id for user in event_users]
        for uid in users_leaving:
            _issue_invite(bot, uid, event.conv_id)


@asyncio.coroutine
def _new_group_conversation(bot, initiator_id):
    _response = yield from bot._client.create_conversation(
        hangups.hangouts_pb2.CreateConversationRequest(
            request_header = bot._client.get_request_header(),
            type = hangups.hangouts_pb2.CONVERSATION_TYPE_GROUP,
            client_generated_id = bot._client.get_client_generated_id(),
            invitee_id = [ hangups.hangouts_pb2.InviteeID(gaia_id = initiator_id) ]))
    new_conversation_id = _response.conversation.conversation_id.id

    yield from bot.coro_send_message(new_conversation_id, _("<i>group created</i>"))
    yield from asyncio.sleep(1) # allow convmem to update
    yield from command.run( bot,
                            event,
                            *[ "convrename",
                               "id:" + new_conversation_id,
                               _("GROUP: {}").format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")) ])
    return new_conversation_id


def _get_invites(bot, filter_active=True, filter_user=False):
    invites = {}
    if bot.memory.exists(["invites"]):
        for invite_id, invite_data in bot.memory["invites"].items():
            if filter_active and time.time() > invite_data["expiry"]:
                continue
            if not filter_active and time.time() < invite_data["expiry"]:
                continue
            if filter_user and invite_data["user_id"] not in ("*", filter_user):
                continue
            invites[invite_id] = invite_data
    return invites


def _get_user_list(bot, conv_id):
    convlist = bot.conversations.get(conv_id)
    return convlist[conv_id]["participants"]


def invite(bot, event, *args):
    """manage invite for users:
    "list", "purge" allows listing and removing invites - add "expired" to view inactive invites
    "from" specifies users from source conversation id - if unset, gets users from current group or list of "users"
    "to" specifies destination conversation id - if unset, uses current group or creates a new one
    "test" to prevent writing anything to storage
    """
    test = False

    everyone = True
    wildcards = 0

    targetconv = False
    sourceconv = False
    list_users = []

    """special cases:
    * test [set flag, then remove parameter]
    * no parameters [error out]
    * 1st parameter is digit [wildcard invite]
    * any parameter is "list" or "purge" [process then return immediately]
    """

    parameters = list(args)

    if "test" in parameters:
        """turn on test mode - prevents writes"""
        test = True
        parameters.remove("test")

    if len(parameters) == 0:
        yield from bot.coro_send_message(event.conv_id, _("<em>insufficient parameters for invite</em>"))
        return

    elif parameters[0].isdigit():
        """wildcard invites can be used by any user with access to the bot
        note: wildcard invite command can still be superseded by specifying a "users" list 
          as a parameter
        """
        wildcards = int(parameters[0])
        if wildcards > 0 and wildcards < 150:
            del(parameters[0])

    elif "list" in parameters or "purge" in parameters:
        """[list] all invites inside the bot memory, and [purge] when requested"""

        lines = []

        if "purge" in parameters:
            if test:
                lines.append(_("<b>Test Invitation Purge</b>"))
            else:
                lines.append(_("<b>Invitation Purge</b>"))
            _mode = "purge"
        else:
            lines.append(_("<b>Invitation List</b>"))
            _mode = "list"

        if "expired" in parameters:
            _active_only = False
        else:
            _active_only = True

        active_invites = _get_invites(bot, filter_active=_active_only)

        if len(active_invites) > 0:
            for _id, invite in active_invites.items():
                try:
                    conversation_name = bot.conversations.get_name(invite["group_id"])
                except ValueError:
                    conversation_name = "? ({})".format(invite["group_id"])

                user_id = invite["user_id"]
                if user_id == "*":
                    user_id = "anyone"

                if not test and _mode == "purge":
                    _remove_invite(bot, invite["id"])

                expiry_in_days = round((invite["expiry"] - time.time()) / 86400, 1)
                lines.append("<i><pre>{}</pre></i> to <b><pre>{}</pre></b> ... {} ({} days left)".format(
                    user_id, conversation_name, invite["id"], expiry_in_days))

        else:
            lines.append(_("<em>no invites found</em>"))

        yield from bot.coro_send_message(event.conv_id, "<br />".join(lines))
        return

    """process parameters sequentially using a finite state machine"""

    state = ["users"]
    for parameter in parameters:
        if parameter in ("to", "from", "users"):
            state.append(parameter)
        else:
            if state[-1] == "to":
                targetconv = parameter
                state.pop()
            elif state[-1] == "from":
                sourceconv = parameter
                state.pop()
            elif state[-1] == "users":
                list_users.append(parameter)
                everyone = False # filter invitees by list_users
                wildcards = 0 # turn off wildcard invites
            else:
                raise ValueError("UNKNOWN STATE: {}".format(state[-1]))

    """ensure supplied conversations are consistent"""

    if not targetconv and not sourceconv:
        """
        from = None, to = None:
            sourceconv = current
            targetconv = new blank conversation
        """
        sourceconv = event.conv_id
        targetconv = "NEW_GROUP"

    elif not targetconv:
        """
        from = current, to = None:
            sourceconv = current
            targetconv = new blank conversation
        from = other, to = None:
            sourceconv = other
            targetconv = current (or new, if not GROUP)
        """
        if sourceconv == event.conv_id:
            targetconv = "NEW GROUP"
        else:
            if bot.conversations.catalog[event.conv_id]["type"] != "GROUP":
                targetconv = "NEW_GROUP"
            else:
                targetconv = event.conv_id

    elif not sourceconv:
        """
        list_users = 0:
            from = None, to = current:
                ERROR
            from = None, to = other:
                sourceconv = current
                targetconv = other
        list_users > 0:
            sourceconv = None
            targetconv = *
        """
        if len(list_users) == 0:
            if targetconv == event.conv_id:
                yield from bot.coro_send_message(event.conv_id,
                    _('<em>invite: specify "from" or explicit list of "users"</em>'))
                return
            else:
                sourceconv = event.conv_id

    """sanity checking"""

    if targetconv != "NEW_GROUP" and targetconv not in bot.conversations.get():
        yield from bot.coro_send_message(event.conv_id,
            _('<em>invite: could not identify target conversation'))
        return

    """invitation generation"""

    invitation_log = [] # devnote: no more returns after this line!

    invitation_log.append("source conv: {}, target conv: {}".format(sourceconv, targetconv))
    invitation_log.append("user list = [{}]".format(len(list_users)))

    invitations = []

    if wildcards > 0:
        """wildcards can be used by any user to enter a targetconv"""
        invitations.append({ 
            "user_id": "*", 
            "uses": wildcards })

        invitation_log.append("wildcard invites: ".format(wildcards))
        logger.info("convtools_invitations: {} wildcard invite for {}".format(wildcards, targetconv))

    else:
        """shortlist users from source room, or explicit list_users"""
        shortlisted = []
        if sourceconv:
            sourceconv_users = _get_user_list(bot, sourceconv)
            for chat_id in sourceconv_users:
                if everyone or chat_id in list_users:
                    shortlisted.append(chat_id)

            invitation_log.append("shortlisted: {}/{}".format(len(shortlisted), len(sourceconv_users)))
            logger.info("convtools_invitations: shortlisted {}/{} from {}, everyone={}, list_users=[{}]".format(
                len(shortlisted), len(sourceconv_users), sourceconv, everyone, len(list_users)))

        else:
            shortlisted = list_users

            invitation_log.append("direct list: {}".format(len(shortlisted)))
            logger.info("convtools_invitations: shortlisted {}".format(len(shortlisted), sourceconv))

        """exclude users who are already in the target conversation"""
        if targetconv == "NEW_GROUP":
            # fake user list - _new_group_conversation() always creates group with bot and initiator
            targetconv_users = [ event.user.id_.chat_id, bot.user_self()["chat_id"] ]
        else:
            targetconv_users = _get_user_list(bot, targetconv)
        invited_users = []
        for uid in shortlisted:
            if uid not in targetconv_users:
                invited_users.append(uid)
            else:
                invitation_log.append("excluding existing: {}".format(uid))
                logger.info("convtools_invitations: rejecting {}, already in {}".format(uid, targetconv))
        invited_users = list(set(invited_users))

        logger.info("convtools_invitations: inviting {} to {}".format(len(invited_users), targetconv))

        for uid in invited_users:
            invitations.append({
                "user_id": uid, 
                "uses": 1 })

    """beyond this point, start doing irreversible things (like create groups)"""

    if len(invitations) == 0:
        yield from bot.coro_send_message(event.conv_id,
            _('<em>invite: nobody invited</em>'))

        invitation_log.append("no invitations were created")
        logger.info("convtools_invitations: nobody invited, aborting...")

    else:
        """create new conversation (if required)"""

        if targetconv == "NEW_GROUP":
            invitation_log.append("create new group")
            if not test:
                targetconv = yield from _new_group_conversation(bot, event.user.id_.chat_id)

        """issue the invites"""

        invitation_ids = []
        for invite in invitations:
            invitation_log.append("invite {} to {}, uses: {}".format(
                invite["user_id"], targetconv, invite["uses"]))
            if not test:
                # invites are not created in test mode
                invitation_ids.append(
                    _issue_invite(bot, invite["user_id"], targetconv, invite["uses"]))

        if len(invitation_ids) > 0:
            yield from bot.coro_send_message(event.conv_id, 
                _("<em>invite: {} invitations created</em>").format(len(invitation_ids)))

    if test:
        invitation_log.insert(0, "<b>Invite Test Mode</b>")
        yield from bot.coro_send_message(event.conv_id, 
            "<br />".join(invitation_log))


def rsvp(bot, event, *args):
    """show/claim invite codes"""

    if len(args) == 1:
        yield from _claim_invite(bot, args[0], event.user.id_.chat_id)

    else:
        active_invites = _get_invites(bot, filter_user=event.user.id_.chat_id, filter_active=True)

        if len(active_invites) > 0:
            lines = []
            lines.append(_("<b>Invites for {}:</b>").format(event.user.full_name))
            for _id, invite in active_invites.items():
                conversation_name = bot.conversations.get_name(invite["group_id"])
                expiry_in_days = round((invite["expiry"] - time.time()) / 86400, 1)
                lines.append("<b>{}</b> ... {} ({} days left)".format(conversation_name, invite["id"], expiry_in_days))
            lines.append(_("<em>To claim an invite, use the rsvp command followed by the invite code</em>"))
            yield from bot.coro_send_message(event.conv_id, "<br />".join(lines))
        else:
            yield from bot.coro_send_message(event.conv_id, _("<em>no invites to display</em>"))
