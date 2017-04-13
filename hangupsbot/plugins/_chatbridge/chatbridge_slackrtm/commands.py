from functools import wraps
import re


bridge = None

def set_bridge(br):
    global bridge
    bridge = br


def _respond_privately(fn):
    @wraps(fn)
    def wrap(bot, event, *args):
        # If the command generates a response, send it privately to the user.
        resp = fn(bot, event, *args)
        if not resp:
            return
        conv = yield from bot.get_1to1(event.user.id_.chat_id)
        # Replace uses of /bot with the bot's alias.
        botalias = (bot.memory.get("bot.command_aliases") or ["/bot"])[0]
        yield from bot.coro_send_message(conv, re.sub(r"(^|\s|>)/bot\b", r"\1{}".format(botalias), resp))
    return wrap


@_respond_privately
def slack_identify(bot, event, *args):
    ("""Create a link between your Hangouts and Slack profiles.<br>"""
     """Identify as a Slack user: <b>/bot slack_identify as <i>team</i> <i>user</i></b><br>"""
     """Clear an identity: <b>/bot slack_identify clear <i>team</i></b>""")
    if not args or (args[0], len(args)) not in [("as", 3), ("clear", 2)]:
        return ("<b>Usage:</b>\n"
                "/bot slack_identify as <i>team</i> <i>user</i>\n"
                "/bot slack_identify clear <i>team</i>")
    identity = event.user.id_.chat_id
    team = args[1]
    if team not in bridge.slacks:
        return "No Slack team called <b>{}</b>.".format(team)
    idents = bridge.idents[team]
    if args[0] == "as":
        user_query = args[2]
        for user_id, user in bridge.slacks[team].users.items():
            if user_query == user["id"] or user_query.lower() == user["name"]:
                break
        else:
            return "No user in <b>{}</b> called <b>{}</b>.".format(team, user_query)
        if idents.get_hangouts(identity) == user_id:
            resp = "You are already identified as <b>{}</b>.".format(user["name"])
            if not idents.get_slack(user_id) == identity:
                resp += "\nBut you still need to confirm your identity from Slack."
            return resp
        idents.add_hangouts(identity, user_id)
        resp = "You have identified as <b>{}</b> on <b>{}</b>.".format(args[2], args[1])
        if not idents.get_slack(user_id) == identity:
            resp += "\nNow you need to confirm your identity from Slack."
        return resp
    elif args[0] == "clear":
        if idents.get_hangouts(identity):
            idents.del_hangouts(identity)
            return "Slack identity cleared."
        else:
            return "No identity set for <b>{}</b>.".format(team)
