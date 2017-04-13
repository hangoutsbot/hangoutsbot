from functools import wraps
import logging
import re

from plugins.slackrtm.parsers import slack_markdown_to_hangups

from .core import HANGOUTS, SLACK, inv


logger = logging.getLogger(__name__)


bridge = None

def set_bridge(br):
    """
    Obtain a reference to the bridge instance for use with commands.
    """
    global bridge
    bridge = br


def identify(source, sender, team, query=None, clear=False):
    """
    Create one side of an identity link, either Hangouts->Slack or Slack->Hangouts.
    """
    dest = inv(source)
    idents = bridge.idents[team]
    if query:
        if source == HANGOUTS:
            for user_id, user in bridge.users[team].items():
                if query == user["id"] or query.lower() == user["name"]:
                    user_name = user["name"]
                    break
            else:
                return "No user in {} called *{}*.".format(dest, query)
        else:
            user = bridge.bot.get_hangups_user(query)
            if not user.definitionsource:
                return "No user in {} with ID *{}*.".format(dest, query)
            user_id = user.id_.chat_id
            user_name = user.full_name
        if idents.get(source, sender) == user_id:
            resp = "You are already identified as *{}*.".format(user_name)
            if not idents.get(dest, user_id) == sender:
                resp += "\nBut you still need to confirm your identity from {}.".format(dest)
            return resp
        idents.add(source, sender, user_id)
        resp = "You have identified as *{}*.".format(user_name)
        if not idents.get(dest, user_id) == sender:
            resp += "\nNow you need to confirm your identity from {}.".format(dest)
        return resp
    elif clear:
        if idents.get(source, sender):
            idents.remove(source, sender)
            return "{} identity cleared.".format(dest)
        else:
            return "No identity set."


def reply_hangouts(fn):
    """
    Decorator: run a bot comand, and send the result privately to the calling Hangouts user.
    """
    @wraps(fn)
    def wrap(bot, event, *args):
        resp = slack_markdown_to_hangups(fn(bot, event, *args))
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
    @wraps(fn)
    def wrap(msg, slack, team):
        resp = fn(msg, slack, team)
        if not resp:
            return
        slack.api_call("chat.postMessage", channel=msg.channel, as_user=True, text=resp)
    return wrap


@reply_hangouts
def slack_identify(bot, event, *args):
    ("""Link your Hangouts identity to a Slack team.\n"""
     """<b>slack_identify as <i>team</i> <i>user</i></b> to link, <b>slack_identify clear <i>team</i></b> to unlink.""")
    if not len(args) or (args[0].lower(), len(args)) not in [("as", 3), ("clear", 2)]:
        return "Usage: *slack_identify as _team_ _user_* to link, *slack_identify clear _team_* to unlink"
    if args[0].lower() == "as":
        kwargs = {"query": args[2]}
    else:
        kwargs = {"clear": True}
    return identify(HANGOUTS, event.user.id_.chat_id, args[1], **kwargs)


@reply_slack
def run_slack_command(msg, slack, team):
    args = msg.text.split()
    try:
        name = args.pop(0)
    except IndexError:
        return
    if name == "identify":
        if not len(args) or (args[0].lower(), len(args)) not in [("as", 2), ("clear", 1)]:
            return "Usage: *identify as _user_* to link, *identify clear* to unlink"
        if args[0].lower() == "as":
            kwargs = {"query": args[1]}
        else:
            kwargs = {"clear": True}
        return identify(SLACK, msg.user, team, **kwargs)
