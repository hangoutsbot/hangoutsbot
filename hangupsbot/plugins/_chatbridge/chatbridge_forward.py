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
        source_action = external_context.get("source_action", False)
        source_edited = external_context.get("source_edited", False)

        show_source = self.configuration[conv_id].get("show_source", True)
        show_sender = self.configuration[conv_id].get("show_sender", False)

        text = ""
        if show_source:
            text += "<b>{}</b>".format(source_title)
            if source_edited and not show_sender:
                text += " (edited)"
            text += "<br>"
        if show_sender:
            text += "<b>{}</b>".format(bridge_user["preferred_name"])
            if source_edited:
                text += " (edited)"
            if not source_action:
                text += ":"
            text += " "
        text += message
        if source_action:
            text = "<i>{}</i>".format(text)

        return text


def _initialise(bot):
    BridgeInstance(bot, "forwarding")
