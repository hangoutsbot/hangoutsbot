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


    def format_incoming_message(self, message, external_context):
        conv_id = external_context["source_gid"]

        source_user = external_context.get("source_user") or self.plugin_name
        bridge_user = self._get_user_details(source_user, external_context)
        source_title = external_context.get("source_title")

        show_source = self.configuration[conv_id].get("show_source", True)
        show_sender = self.configuration[conv_id].get("show_sender", False)

        source = "<b>{}</b><br/>".format(source_title) if show_source else ""
        sender = "<b>{}</b>".format(bridge_user["preferred_name"]) if show_sender else ""
        if sender and external_context.get("source_edited"):
            sender = "{} (edited)".format(sender)

        template = "<i>{}{} {}</i>" if external_context.get("source_action") else "{}{}: {}"
        return template.format(source, sender, message)


def _initialise(bot):
    BridgeInstance(bot, "forwarding")
