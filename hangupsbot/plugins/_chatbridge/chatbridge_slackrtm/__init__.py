import plugins

from .bridge import BridgeInstance, on_membership_change
from .core import Base, Slack
from .commands import slack_identify, slack_sync, slack_unsync
from .utils import convert_legacy_config


def _initialise(bot):
    convert_legacy_config(bot)
    plugins.register_user_command(["slack_identify"])
    plugins.register_admin_command(["slack_sync", "slack_unsync"])
    root = bot.get_config_option("slackrtm") or {}
    Base.bot = bot
    for team, config in root.get("teams", {}).items():
        Base.add_slack(Slack(team, config["token"]))
    for sync in root.get("syncs", []):
        Base.add_bridge(BridgeInstance(bot, "slackrtm", sync))
    for slack in Base.slacks.values():
        slack.start()
    plugins.register_handler(on_membership_change, type="membership")

def _finalise(bot):
    for slack in list(Base.slacks.values()):
        Base.remove_slack(slack)
    Base.bot = None
