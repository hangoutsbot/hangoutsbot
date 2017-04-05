import asyncio
import logging
import re

from webbridge import ( WebFramework,
                        FakeEvent )

from .utils import ( _slackrtms,
                     _slackrtm_conversations_get )


logger = logging.getLogger(__name__)


class BridgeInstance(WebFramework):
    def setup_plugin(self):
        self.plugin_name = "slackRTM"

    def set_extra_configuration(self, hangouts_id, channel_id):
        """in slackrtm, bridgeinstances are attached to individual 1-1 hangouts/slack mappings
            parameters set during SlackRTMSync instantiation, used to filter applicable configurations"""

        self.hangouts_id = hangouts_id
        self.channel_id = channel_id

    def applicable_configuration(self, conv_id):
        """because of the object hierachy of original slackrtm, each bridgeinstance cannot maintain
            knowledge of the entire configuration, only return a single applicable configuration"""

        if conv_id != self.hangouts_id:
            return []

        self.load_configuration(self.configkey)

        applicable_configurations = []
        for configuration in self.configuration:
            if( conv_id in configuration["hangouts"]
                    and self.channel_id in configuration[self.configkey] ):
                applicable_configurations.append({ "trigger": conv_id,
                                                   "config.json": configuration })

        return applicable_configurations

    def load_configuration(self, configkey):
        """mutate the slack configuration earlier, maintain 1-1 mappings, so that we can filter
        it later for a single hangouts and slack channel mapping"""

        slackrtm_configs = self.bot.get_config_option(configkey) or []
        if not slackrtm_configs:
            return

        mutated_configurations = []
        for slackrtm_config in slackrtm_configs:
            # mutate the config earlier, as slackrtm is messy
            synced_conversations = _slackrtm_conversations_get(self.bot, slackrtm_config["name"]) or []
            for synced in synced_conversations:
                config_clone = dict(slackrtm_config)
                config_clone["hangouts"] = [ synced["hangoutid"] ]
                config_clone[configkey] = [ synced["channelid"] ]
                mutated_configurations.append(config_clone)
        self.configuration = mutated_configurations

        return self.configuration

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        conv_id = config["trigger"]
        channel_id = config["config.json"]["slackrtm"][0]
        team_name = config["config.json"]["name"]

        """slackrtm uses one thread per team, identify slackclient to handle the hangouts message.
        since the config is further separated by hangouts conv_id for relay, we also supply extra info
            to the handler, so it can decide for itself whether/where the message should be forwarded"""

        logger.info("{}:{}:_send_to_external_chat, slackrtms = {}".format(self.plugin_name, self.uid, len(_slackrtms)))

        for slackrtm in _slackrtms:
            try:
                # identify the correct thread, then send the message
                if slackrtm.name == team_name:
                    yield from slackrtm.handle_ho_message(event, conv_id, channel_id)
            except Exception as e:
                logger.exception(e)

    def format_incoming_message(self, message, external_context):
        sync = external_context["sync"]
        source_user = external_context["source_user"]
        source_title = external_context["source_title"]

        if sync.slacktag is False or sync.slacktag is None:
            source_title = False
        elif sync.slacktag is not True and sync.slacktag:
            source_title = sync.slacktag
        else:
            # use supplied channel title
            pass

        if source_title:
            formatted = "<b>{}</b> ({}): {}".format( source_user,
                                                     source_title,
                                                     message )
        else:
            formatted = "<b>{}</b>: {}".format( source_user, message )

        return formatted

    def map_external_uid_with_hangups_user(self, source_uid, external_context):
        sync = external_context["sync"]
        team_name = sync.team_name
        slack_uid = source_uid

        hangups_user = False
        try:
            hangouts_uid = self.bot.memory.get_by_path([ "slackrtm", team_name, "identities", "slack", slack_uid ])

            # security: the mapping must be bi-directional and point to each other
            mapped_slack_uid = self.bot.memory.get_by_path([ "slackrtm", team_name, "identities", "hangouts", hangouts_uid ])
            if mapped_slack_uid != slack_uid:
                return False

            _hangups_user = self.bot.get_hangups_user(hangouts_uid)
            if _hangups_user.definitionsource:
                hangups_user = _hangups_user
        except KeyError:
            logger.info("no hangups user for {} {}".format(team_name, slack_uid))

        return hangups_user

    def start_listening(self, bot):
        """slackrtm does not use web-bridge style listeners"""
        pass
