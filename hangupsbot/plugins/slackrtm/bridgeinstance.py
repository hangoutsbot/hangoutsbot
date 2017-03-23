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

    def load_configuration(self, configkey):
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
        team_name = config["config.json"]["name"]

        user = event.passthru["original_request"]["user"]
        message = event.passthru["original_request"]["message"]

        """slackrtm uses one thread per team, identify slackclient to handle the hangouts message.
        since the config is further separated by hangouts conv_id for relay, we also supply extra info
            to the handler, so it can decide for itself whether/where the message should be forwarded"""

        for slackrtm in _slackrtms:
            try:
                # identify the correct thread, then send the message
                if slackrtm.name == team_name:
                    yield from slackrtm.handle_ho_message(event, conv_id)
            except Exception as e:
                logger.exception(e)

    def format_incoming_message(self, message, external_context):
        sync = external_context["sync"]
        source_user = external_context["source_user"]
        source_title = external_context["source_title"]

        if sync.slacktag is False:
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

    def start_listening(self, bot):
        """slackrtm does not use web-bridge style listeners"""
        pass
