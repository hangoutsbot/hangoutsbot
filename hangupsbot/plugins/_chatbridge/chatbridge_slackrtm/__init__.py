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
        Base.add_slack(team, Slack(team, config["token"]))
    for sync in root.get("syncs", []):
        Base.add_bridge(BridgeInstance(bot, "slackrtm", sync))
    for slack in Base.slacks.values():
        plugins.start_asyncio_task(slack.loop())
    plugins.register_handler(on_membership_change, type="membership")
