import asyncio
from functools import wraps
import logging
import re

from .core import HANGOUTS, SLACK, inv, Base
from .parser import from_hangups


logger = logging.getLogger(__name__)


def _resolve_channel(team, query):
    # Match Slack channel hyperlinks.
    match = re.match(r"<#(.*?)\|.*?>", query)
    if match:
        query = match.group(1)
    if query in Base.slacks[team].channels:
        return Base.slacks[team].channels[query]
    if query.startswith("#"):
        query = query[1:]
    for channel in Base.slacks[team].channels.values():
        if channel["name"] == query:
            return channel
    raise KeyError(query)


def identify(source, sender, team, query=None, clear=False):
    """
    Create one side of an identity link, either Hangouts->Slack or Slack->Hangouts.
    """
    dest = inv(source)
    idents = Base.idents[team]
    slack = Base.slacks[team]
    if query:
        if source == HANGOUTS:
            for user_id, user in slack.users.items():
                if query == user["id"] or query.lower() == user["name"]:
                    user_name = user["name"]
                    break
            else:
                return "No user in <b>{}</b> called <b>{}</b>.".format(team, query)
        else:
            user = Base.bot.get_hangups_user(query)
            if not user.definitionsource:
                return "No user in Hangouts with ID <b>{}</b>.".format(query)
            user_id = user.id_.chat_id
            user_name = user.full_name
        if idents.get(source, sender) == user_id:
            resp = "You are already identified as <b>{}</b>.".format(user_name)
        else:
            idents.add(source, sender, user_id)
            resp = "You have identified as <b>{}</b>.".format(user_name)
        if not idents.get(dest, user_id) == sender:
            resp += "\nConfirm your identity from {} with this command:".format(dest)
            if dest == HANGOUTS:
                cmd = "/bot slack_identify as {} {}".format(team, slack.users[sender]["name"])
            else:
                cmd = "identify as {}".format(sender)
            resp += "\n<b>{}</b>".format(cmd)
        return resp
    elif clear:
        if idents.get(source, sender):
            idents.remove(source, sender)
            return "{} identity cleared.".format(dest)
        else:
            return "No identity set."


def sync(team, channel, hangout):
    """
    Store a new Hangouts<->Slack sync, taking immediate effect.
    """
    try:
        channel = _resolve_channel(team, channel)
    except KeyError:
        return "No such channel <b>{}</b> on <b>{}</b>.".format(channel, team)
    # Make sure this team/channel/hangout combination isn't already configured.
    for bridge in Base.bridges[team]:
        if bridge.team == team and bridge.channel == channel["id"] and bridge.hangout == hangout:
            return "This channel/hangout pair is already being synced."
    # Create a new bridge, and register it with the Slack connection.
    # XXX: Circular dependency on bridge.BridgeInstance, commands.run_slack_command.
    from .bridge import BridgeInstance
    sync = {"channel": [team, channel["id"]], "hangout": hangout}
    Base.add_bridge(BridgeInstance(Base.bot, "slackrtm", sync))
    # Add the new sync to the config list.
    syncs = Base.bot.config.get_by_path(["slackrtm", "syncs"])
    syncs.append(sync)
    Base.bot.config.set_by_path(["slackrtm", "syncs"], syncs)
    return "Now syncing <b>#{}</b> on <b>{}</b> to hangout <b>{}</b>.".format(channel["name"], team, hangout)

def unsync(team, channel, hangout):
    """
    Remove an existing Hangouts<->Slack sync, taking immediate effect.
    """
    try:
        channel = _resolve_channel(team, channel)
    except KeyError:
        return "No such channel <b>{}</b> on <b>{}</b>.".format(channel, team)
    # Make sure this team/channel/hangout combination isn't already configured.
    for bridge in Base.bridges[team]:
        if bridge.team == team and bridge.channel == channel["id"] and bridge.hangout == hangout:
            # Remove the sync from the config list.
            syncs = Base.bot.config.get_by_path(["slackrtm", "syncs"])
            syncs.remove(bridge.sync)
            Base.bot.config.set_by_path(["slackrtm", "syncs"], syncs)
            # Destroy the bridge and its event callback.
            Base.remove_bridge(bridge)
            return ("No longer syncing <b>#{}</b> on <b>{}</b> to hangout <b>{}</b>."
                    .format(channel["name"], team, hangout))
    return "This channel/hangout pair isn't currently being synced."


def reply_hangouts(fn):
    """
    Decorator: run a bot comand, and send the result privately to the calling Hangouts user.
    """
    @wraps(fn)
    def wrap(bot, event, *args):
        resp = fn(bot, event, *args)
        if not resp:
            return
        conv = yield from bot.get_1to1(event.user.id_.chat_id)
        # Replace uses of /bot with the bot's alias.
        botalias = (bot.memory.get("bot.command_aliases") or ["/bot"])[0]
        yield from bot.coro_send_message(conv, re.sub(r"(^|\s|>)/bot\b", r"\1{}".format(botalias), resp))
    return wrap

def reply_slack(fn):
    """
    Decorator: run a Slack command, and send the result privately to the calling Slack user.
    """
    @asyncio.coroutine
    def wrap(msg, slack):
        resp = fn(msg, slack)
        if not resp:
            return
        yield from slack.msg(channel=msg.channel, as_user=True, text=from_hangups.convert(resp, slack))
    return wrap


@reply_hangouts
def slack_identify(bot, event, *args):
    ("""Link your Hangouts identity to a Slack team.\nUsage: """
     """<b>slack_identify as <i>team</i> <i>user</i></b> to link, <b>slack_identify clear <i>team</i></b> to unlink.""")
    if not len(args) or (args[0].lower(), len(args)) not in [("as", 3), ("clear", 2)]:
        return "Usage: <b>slack_identify as <i>team user</i></b> to link, <b>slack_identify clear <i>team</i></b> to unlink"
    if args[0].lower() == "as":
        kwargs = {"query": args[2]}
    else:
        kwargs = {"clear": True}
    return identify(HANGOUTS, event.user.id_.chat_id, args[1], **kwargs)

@reply_hangouts
def slack_sync(bot, event, *args):
    ("""Link a Slack channel to a hangout.\nUsage: <b>slack_sync <i>team</i> <i>channel</i> to <i>hangout</i></b>, """
     """or just <b>slack_sync <i>team</i> <i>channel</i></b> for the current hangout.""")
    if not (len(args) == 2 or len(args) == 4 and args[2] == "to"):
        return ("Usage: <b>slack_sync <i>team channel</i> to <i>hangout</i></b>, "
                "or just <b>slack_sync <i>team channel</i></b> for the current hangout.")
    return sync(args[0], args[1], event.conv.id_ if len(args) == 2 else args[3])

@reply_hangouts
def slack_unsync(bot, event, *args):
    ("""Unlink a Slack channel from a hangout.\nUsage: <b>slack_unsync <i>team</i> <i>channel</i> from <i>hangout</i></b>, """
     """or just <b>slack_unsync <i>team</i> <i>channel</i></b> for the current hangout.""")
    if not (len(args) == 2 or len(args) == 4 and args[2] == "from"):
        return ("Usage: <b>slack_unsync <i>team channel</i> from <i>hangout</i></b>, "
                "or just <b>slack_unsync <i>team channel</i></b> for the current hangout.")
    return unsync(args[0], args[1], event.conv.id_ if len(args) == 2 else args[3])


@reply_slack
def run_slack_command(msg, slack):
    args = msg.text.split()
    try:
        name = args.pop(0)
    except IndexError:
        return
    try:
        admins = Base.bot.config.get_by_path(["slackrtm", "teams", slack.name, "admins"])
    except (KeyError, TypeError):
        admins = []
    if name == "identify":
        if not len(args) or (args[0].lower(), len(args)) not in [("as", 2), ("clear", 1)]:
            return "Usage: <b>identify as <i>user</i></b> to link, <b>identify clear</b> to unlink"
        if args[0].lower() == "as":
            kwargs = {"query": args[1]}
        else:
            kwargs = {"clear": True}
        return identify(SLACK, msg.user, slack.name, **kwargs)
    elif msg.user in admins:
        if name == "sync":
            if not (len(args) == 3 and args[1] == "to"):
                return "Usage: <b>sync <i>channel</i> to <i>hangout</i></b>"
            return sync(slack.name, args[0], args[2])
        elif name == "unsync":
            if not (len(args) == 3 and args[1] == "from"):
                return "Usage: <b>unsync <i>channel</i> from <i>hangout</i></b>"
            return unsync(slack.name, args[0], args[2])
