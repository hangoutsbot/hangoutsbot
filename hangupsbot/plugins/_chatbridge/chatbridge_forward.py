import logging

from plugins._chatbridge.chatbridge_syncrooms import BridgeInstance as SyncroomsBridgeInstance

logger = logging.getLogger(__name__)


class BridgeInstance(SyncroomsBridgeInstance):

    def setup_plugin(self):
        self.plugin_name = "forwarding"

    def applicable_configuration(self, conv_id):
        """
        "forwarding": {
            "<source HO>": {
                "enabled": true,
                "show_sender": false,
                "show_source": true,
                "targets": [
                    "<destination HO>",
                    "<destination HO>",
                    ...
                ]
            },
            ...
        }

        Defaults for enabled, show_sender, show_source as shown.
        """
        self.load_configuration(self.configkey)

        applicable_configurations = []
        for source, forward in self.configuration.items():
            if not forward.get("enabled", True):
                continue
            if conv_id == source and forward.get("targets"):
                applicable_configurations.append({"trigger": conv_id,
                                                  "config.json": {"hangouts": forward["targets"]}})

        return applicable_configurations

    # _send_to_external_chat() inherited from syncrooms


def _initialise(bot):
    BridgeInstance(bot, "forwarding")
