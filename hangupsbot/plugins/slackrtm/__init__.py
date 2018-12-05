"""
Improved Slack sync plugin using the Slack RTM API instead of webhooks.
(c) 2015 Patrick Cernko <errror@gmx.de>


Create a Slack bot integration (not webhooks!) for each team you want
to sync into hangouts.

Your config.json should have a slackrtm section that looks something
like this.  You only need one entry per Slack team, not per channel,
unlike the legacy code.

    "slackrtm": [
        {
            "name": "SlackTeamNameForLoggingCommandsEtc",
            "key": "SLACK_TEAM1_BOT_API_KEY",
            "admins": [ "U01", "U02" ]
        },
        {
            "name": "OptionalSlackOtherTeamNameForLoggingCommandsEtc",
            "key": "SLACK_TEAM2_BOT_API_KEY",
            "admins": [ "U01", "U02" ]
        }
    ]

name = slack team name
key = slack bot api key for that team (xoxb-xxxxxxx...)
admins = user_id from slack (you can use https://api.slack.com/methods/auth.test/test to find it)

You can set up as many slack teams per bot as you like by extending the list.

Once the team(s) are configured, and the hangupsbot is restarted, invite
the newly created Slack bot into any channel or group that you want to sync,
and then use the command:
    @botname syncto <hangoutsid>

Use "@botname help" for more help on the Slack side and /bot help <command> on
the Hangouts side for more help.

"""

import asyncio
import logging

import plugins

from .commands_hangouts import ( slacks,
                                 slack_channels,
                                 slack_users,
                                 slack_listsyncs,
                                 slack_syncto,
                                 slack_disconnect,
                                 slack_setsyncjoinmsgs,
                                 slack_setimageupload,
                                 slack_sethotag,
                                 slack_setslacktag,
                                 slack_showslackrealnames,
                                 slack_showhorealnames,
                                 slack_identify )
from .core import SlackRTMThread
from .utils import _slackrtms


logger = logging.getLogger(__name__)


def _initialise(bot):
    # unbreak slackrtm memory.json usage
    #   previously, this plugin wrote into "user_data" key to store its internal team settings
    _slackrtm_conversations_migrate_20170319(bot)

    # Start and asyncio event loop
    loop = asyncio.get_event_loop()
    slack_sink = bot.get_config_option('slackrtm')
    threads = []
    if isinstance(slack_sink, list):
        for sinkConfig in slack_sink:
            # start up slack listener in a separate thread
            t = SlackRTMThread(bot, loop, sinkConfig)
            t.daemon = True
            t.start()
            t.isFullyLoaded.wait()
            threads.append(t)
    logger.info("%d sink thread(s) started", len(threads))

    plugins.register_handler(_handle_membership_change, type="membership")
    plugins.register_handler(_handle_rename, type="rename")

    plugins.register_admin_command([ "slacks",
                                     "slack_channels",
                                     "slack_listsyncs",
                                     "slack_syncto",
                                     "slack_disconnect",
                                     "slack_setsyncjoinmsgs",
                                     "slack_setimageupload",
                                     "slack_sethotag",
                                     "slack_users",
                                     "slack_setslacktag",
                                     "slack_showslackrealnames",
                                     "slack_showhorealnames" ])

    plugins.register_user_command([ "slack_identify" ])

    plugins.start_asyncio_task(_wait_until_unloaded).add_done_callback(_plugin_unloaded)

def _slackrtm_conversations_migrate_20170319(bot):
    memory_root_key = "slackrtm"
    if bot.memory.exists([ memory_root_key ]):
        return

    configurations = bot.get_config_option('slackrtm') or []
    migrated_configurations = {}
    for configuration in configurations:
        team_name = configuration["name"]
        broken_path = [ 'user_data', team_name ]
        if bot.memory.exists(broken_path):
            legacy_team_memory = dict(bot.memory.get_by_path(broken_path))
            migrated_configurations[ team_name ] = legacy_team_memory

    bot.memory.set_by_path([ memory_root_key ], migrated_configurations)
    bot.memory.save()

@asyncio.coroutine
def _wait_until_unloaded(bot):
    while True:
        yield from asyncio.sleep(60)

def _plugin_unloaded(future):
    pass

@asyncio.coroutine
def _handle_membership_change(bot, event, command):
    for slackrtm in _slackrtms:
        try:
            slackrtm.handle_ho_membership(event)
        except Exception as e:
            logger.exception('_handle_membership_change threw: %s', str(e))


@asyncio.coroutine
def _handle_rename(bot, event, command):
    if not _slackrtms:
        return
    for slackrtm in _slackrtms:
        try:
            slackrtm.handle_ho_rename(event)
        except Exception as e:
            logger.exception('_handle_rename threw: %s', str(e))
