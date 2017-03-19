import asyncio
import logging

from webbridge import ( WebFramework,
                        FakeEvent )

from .utils import ( _slackrtms,
                     _slackrtm_conversations_get )


logger = logging.getLogger(__name__)


class BridgeInstance(WebFramework):
    def setup_plugin(self):
        self.plugin_name = "slackRTM"

    def load_configuration(self, convid):
        slackrtm_configs = self.bot.get_config_option('slackrtm') or []
        if not slackrtm_configs:
            return

        """WARNING: slackrtm configuration in current form is FUNDAMENTALLY BROKEN since it misuses USER memory for storage"""

        mutated_configurations = []
        for slackrtm_config in slackrtm_configs:
            # mutate the config earlier, as slackrtm is messy
            config_clone = dict(slackrtm_config)
            synced_conversations = _slackrtm_conversations_get(self.bot, slackrtm_config["name"]) or []
            for synced in synced_conversations:
                config_clone["hangouts"] = [ synced["hangoutid"] ]
                config_clone[self.configkey] = [ synced["channelid"] ]
                mutated_configurations.append(config_clone)
        self.configuration = mutated_configurations

        return self.configuration

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        conv_id = config["trigger"]
        relay_channels = config["config.json"][self.configkey]

        user = event.passthru["original_request"]["user"]
        message = event.passthru["original_request"]["message"]

        for slackrtm in _slackrtms:
            try:
                yield from slackrtm.handle_ho_message(event, chatbridge_extras={ "conv_id": conv_id })
            except Exception as e:
                logger.exception('_handle_slackout threw: %s', str(e))

    def start_listening(self, bot):
        """slackrtm does not use web-bridge style listeners"""
        pass
