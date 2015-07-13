import time, string, random, asyncio, logging, datetime

import hangups

import plugins


def _initialise(bot):
    plugins.register_admin_command(["invite"])
    plugins.register_user_command(["rsvp"])
    plugins.register_handler(_issue_invite_on_exit, type="membership")


def _remove_invite(bot, invite_code):
    memory_path = ["invites", invite_code]
    if bot.memory.exists(memory_path):
        popped_invitation = bot.memory.pop_by_path(memory_path)
        bot.memory.save()
        print("_remove_invite(): {}".format(popped_invitation))
    else:
        print("_remove_invite(): nothing removed")


def _issue_invite(bot, user_id, group_id, uses=1, expire_in=2592000, expiry=None):
    if not bot.memory.exists(["invites"]):
        bot.memory["invites"] = {}

    invitation = False

    # find existing unexpired invitation by user and group - exact match only
    for _key, _invitation in bot.memory["invites"].items():
        if _invitation["user_id"] == user_id and _invitation["group_id"] == group_id and _invitation["expiry"] > time.time():
            invitation = _invitation
            print("_issue_invite(): found existing invite id: {}".format(invitation["id"]))
            break

    # create new invitation if no match found
    if not invitation:
        while True:
            _id = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6))
            if _id not in bot.memory["invites"]:
                print("_issue_invite(): create new invite id: {}".format(_id))
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
        print("_claim_invite(): adding {} to {}".format(user_id, invitation["group_id"]))
        try:
            yield from bot._client.adduser(invitation["group_id"], [user_id])
        except hangups.exceptions.NetworkError as e:
            # trying to add a user to a group where the user is already a member raises this
            print("_CLAIM_INVITE(): FAILED {}".format(e))
            return
        invitation["uses"] = invitation["uses"] - 1
        if invitation["uses"] > 0:
            bot.memory.set_by_path(memory_path, invitation)
            bot.memory.save()
        else:
            _remove_invite(bot, invite_code)
        print("_claim_invite(): claimed {}".format(invitation))
    else:
        print("_claim_invite(): invalid")


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
    response = yield from bot._client.createconversation([initiator_id], force_group=True)
    new_conversation_id = response['conversation']['id']['id']
    bot.send_html_to_conversation(new_conversation_id, _("<i>group created</i>"))
    yield from asyncio.sleep(1) # allow convmem to update
    yield from bot._client.setchatname(new_conversation_id, _("GROUP: {}").format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    return new_conversation_id


def _get_active_invites(bot, filter_user=False):
    active_invites = []
    if bot.memory.exists(["invites"]):
        for invite_id, invite in bot.memory["invites"].items():
            if invite["expiry"] > time.time():
                if not filter_user or invite["user_id"] in ("*", filter_user):
                    active_invites.append(invite)
    return active_invites


def _get_user_list(bot, convid):
    convlist = bot.conversations.get(convid)
    return convlist[convid]["users"]


def invite(bot, event, *args):
    """create invitations for users
    If the 'to' conv_id is not specified then a new conversation is created
    If the 'from' conv_id is not specified then it is assumed to be the current one
    If users are not specified then all users from 'from' conversation are invited

    /bot invite list # Lists all pending invites
    /bot invite purge # Deletes all pending invites
    """
    everyone = True
    wildcards = 0

    targetconv = False
    sourceconv = False
    list_users = []

    """special cases:
    * no parameters [error out]
    * 1st parameter is digit [wildcard invite]
    * any parameter is "list" or "purge" [process then return immediately]
    """

    parameters = list(args)

    if len(parameters) == 0:
        bot.send_html_to_conversation(event.conv_id, _("<em>Usage: https://github.com/hangoutsbot/hangoutsbot/wiki/Conversation-Invitations-Plugin</em>"))
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
        active_invites = _get_active_invites(bot)
        if len(active_invites) > 0:
            lines = []
            for invite in active_invites:
                try:
                    conversation_name = bot.conversations.get_name(invite["group_id"])
                except ValueError:
                    conversation_name = "? ({})".format(invite["group_id"])

                user_id = invite["user_id"]

                if parameters[0] == "purge":
                    _remove_invite(bot, invite["id"])
                    lines.append("<b>REMOVED</b> <i>{}</i>'s invite for <b>{}</b>".format(user_id, conversation_name))
                else:
                    expiry_in_days = round((invite["expiry"] - time.time()) / 86400, 1)
                    lines.append("User <i>{}</i> invited to <b>{}</b> ... {} ({} days left)".format(user_id, conversation_name, invite["id"], expiry_in_days))

            bot.send_html_to_conversation(event.conv_id, "<br />".join(lines))

        else:
            bot.send_html_to_conversation(event.conv_id, _("<em>no invites to list</em>"))

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
                bot.send_html_to_conversation(event.conv_id, 
                    _('<em>invite: specify "from" or explicit list of "users"</em>'))
                return
            else:
                sourceconv = event.conv_id

    """sanity checking"""

    if targetconv != "NEW_GROUP" and targetconv not in bot.conversations.get():
        bot.send_html_to_conversation(event.conv_id, 
            _('<em>invite: could not identify target conversation'))
        return

    """invitation generation"""

    invitations = []

    if wildcards > 0:
        """wildcards can be used by any user to enter a targetconv"""
        invitations.append({ 
            "user_id": "*", 
            "uses": wildcards })

        logging.info("convtools_invitations: {} wildcard invite for {}".format(wildcards, targetconv))

    else:
        """shortlist users from source room, or explicit list_users"""
        shortlisted = []
        if sourceconv:
            sourceconv_users = _get_user_list(bot, sourceconv)
            for u in sourceconv_users:
                if everyone or u[0][0] in list_users:
                    shortlisted.append(u[0][0])

            logging.info("convtools_invitations: shortlisted {}/{} from {}, everyone={}, list_users=[{}]".format(
                len(shortlisted), len(sourceconv_users), sourceconv, everyone, len(list_users)))

        else:
            shortlisted = list_users

            logging.info("convtools_invitations: shortlisted {}".format(len(shortlisted), sourceconv))

        """exclude users who are already in the target conversation"""
        if targetconv == "NEW_GROUP":
            # fake user list - _new_group_conversation() always creates group with bot and initiator
            targetconv_users = [[[event.user.id_.chat_id]], [[bot.user_self()["chat_id"]]]]
        else:
            targetconv_users = _get_user_list(bot, targetconv)
        invited_users = []
        for uid in shortlisted:
            if uid not in [u[0][0] for u in targetconv_users]:
                invited_users.append(uid)
            else:
                logging.info("convtools_invitations: rejecting {}, already in {}".format(uid, targetconv))
        invited_users = list(set(invited_users))

        logging.info("convtools_invitations: inviting {} to {}".format(len(invited_users), targetconv))

        for uid in invited_users:
            invitations.append({
                "user_id": uid, 
                "uses": 1 })

    """last sanity check before we do irreversible things (like create groups)"""

    if len(invitations) == 0:
        bot.send_html_to_conversation(event.conv_id, 
            _('<em>invite: nobody invited</em>'))
        logging.info("convtools_invitations: nobody invited, aborting...")
        return

    """create new conversation (if required)"""

    if targetconv == "NEW_GROUP":
        targetconv = yield from _new_group_conversation(bot, event.user.id_.chat_id)

    """issue the invites"""

    invitation_ids = []
    for invite in invitations:
        invitation_ids.append(
            _issue_invite(bot, invite["user_id"], targetconv, invite["uses"]))

    bot.send_html_to_conversation(event.conv_id, 
        _("<em>invite: {} invitations created</em>").format(len(invitation_ids)))


def rsvp(bot, event, *args):
    """show/claim invite codes"""

    if len(args) == 1:
        yield from _claim_invite(bot, args[0], event.user.id_.chat_id)

    else:
        active_invites = _get_active_invites(bot, filter_user=event.user.id_.chat_id)

        if len(active_invites) > 0:
            lines = []
            lines.append(_("<b>Invites for {}:</b>").format(event.user.full_name))
            for invite in active_invites:
                conversation_name = bot.conversations.get_name(invite["group_id"])
                expiry_in_days = round((invite["expiry"] - time.time()) / 86400, 1)
                lines.append("<b>{}</b> ... {} ({} days left)".format(conversation_name, invite["id"], expiry_in_days))
            lines.append(_("<em>To claim an invite, use the rsvp command followed by the invite code</em>"))
            bot.send_html_to_conversation(event.conv_id, "<br />".join(lines))
        else:
            bot.send_html_to_conversation(event.conv_id, _("<em>no invites to display</em>"))
