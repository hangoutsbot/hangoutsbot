import time
import string
import random
import asyncio

import hangups

from hangups.ui.utils import get_conv_name

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
    if event.conv_event.type_ == hangups.MembershipChangeType.LEAVE:
        event_users = [event.conv.get_user(user_id) for user_id
                       in event.conv_event.participant_ids]
        users_leaving = [user.id_.chat_id for user in event_users]
        for uid in users_leaving:
            _issue_invite(bot, uid, event.conv_id)


def invite(bot, event, *args):
    """create invitations for users"""
    everyone = True
    wildcards = 0

    targetconv = False
    sourceconv = False
    list_users = []

    parameters = list(args)

    if parameters[0].isdigit():
        wildcards = int(parameters[0])
        if wildcards > 0 and wildcards < 150:
            # check allows user ids to pass-through
            del(parameters[0])

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

    if not targetconv and not sourceconv:
        bot.send_html_to_conversation(event.conv_id, _("<em>invite: missing \"to\" or \"from\"</em>"))
        return
    elif not targetconv:
        if sourceconv == event.conv_id:
            bot.send_html_to_conversation(event.conv_id, _("<em>invite: missing \"to\"</em>"))
            return
        else:
            targetconv = event.conv_id
    elif not sourceconv:
        if len(list_users) == 0:
            if targetconv == event.conv_id:
                bot.send_html_to_conversation(event.conv_id, _("<em>invite: specify \"from\" or explicit list of \"users\"</em>"))
                return
            else:
                sourceconv = event.conv_id

    invitations = []

    if wildcards > 0:
        invitations.append(("*", targetconv, wildcards))
    else:
        shortlisted = []
        if sourceconv:
            sourceconv_users = bot.get_users_in_conversation(sourceconv)
            for u in sourceconv_users:
                if everyone or u.id_.chat_id in list_users:
                    shortlisted.append(u.id_.chat_id)
        else:
            shortlisted = list_users

        there = bot.get_users_in_conversation(targetconv)
        invited_users = []
        for uid in shortlisted:
            if uid not in there:
                invited_users.append(uid)

        invited_users = list(set(invited_users))

        if len(invited_users) == 0:
             bot.send_html_to_conversation(event.conv_id, _("<em>invite: nobody invited</em>"))
             return

        for uid in invited_users:
            invitations.append((uid, targetconv))

    invitation_ids = []
    for invite in invitations:
        invitation_ids.append(_issue_invite(bot, *invite))

    bot.send_html_to_conversation(event.conv_id, _("<em>invite: {} invitations created</em>").format(len(invitation_ids)))


def rsvp(bot, event, *args):
    """show/claim invite codes"""

    if len(args) == 1:
        yield from _claim_invite(bot, args[0], event.user.id_.chat_id)
    else:
        invites = []
        if bot.memory.exists(["invites"]):
            for invite_id, invite in bot.memory["invites"].items():
                if invite["user_id"] in ("*", event.user.id_.chat_id):
                    if invite["expiry"] > time.time():
                        invites.append(invite)

        if len(invites) > 0:
            lines = []
            lines.append(_("<b>Invites for {}:</b>").format(event.user.full_name))
            for invite in invites:
                conversation_name = get_conv_name(bot._conv_list.get(invite["group_id"]))
                expiry_in_days = round((invite["expiry"] - time.time()) / 86400, 1)
                lines.append("<b>{}</b> ... {} ({} days left)".format(conversation_name, invite["id"], expiry_in_days))
            lines.append("")
            lines.append(_("<em>To claim an invite, use the rsvp command followed by the invite code</em>"))
            bot.send_html_to_conversation(event.conv_id, "<br />".join(lines))
        else:
            bot.send_html_to_conversation(event.conv_id, _("<em>no invites to display</em>"))