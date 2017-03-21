import aiohttp
import asyncio
import json
import logging
import requests

import plugins

from webbridge import ( WebFramework,
                        FakeEvent )

logger = logging.getLogger(__name__)


class BridgeInstance(WebFramework):
    def setup_plugin(self):
        self.plugin_name = "syncroomsBasic"

    def applicable_configuration(self, conv_id):
        """customised (legacy) configuration structure:

            "syncing_enabled": true,
            "sync_rooms": [
                [
                    "<internal chat/group/team id>",
                    "<internal chat/group/team id>"
                ]
            ]

        """

        if not self.bot.get_config_option('syncing_enabled'):
            return False

        self.load_configuration(self.configkey)

        applicable_configurations = []
        syncouts = self.configuration
        for sync_rooms_list in syncouts:
            if conv_id in sync_rooms_list:
                syncout = list(sync_rooms_list) # clones the list
                syncout.remove(conv_id)
                if syncout:
                    # ensures at least 2 items were in the list, trigger conv_id was removed
                    applicable_configurations.append({ "trigger": conv_id,
                                                       "config.json": { "hangouts": syncout }})

        return applicable_configurations

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        """external chats are just other hangout groups in the same group
        the triggered conv_id was removed by applicable_configuration()
            so we only need to relay to the remaining conv_ids listed
        """

        relay_ids = config["config.json"]["hangouts"]

        user = event.passthru["original_request"]["user"]
        message = event.passthru["original_request"]["message"]
        chat_title = event.passthru["chatbridge"]["source_title"]

        for relay_id in relay_ids:
            yield from self._send_to_internal_chat(
                relay_id,
                message,
                {   "from_user": user,
                    "from_chat": chat_title })

    def start_listening(self, bot):
        """syncrooms do not need any special listeners"""
        pass


def _initialise(bot):
    BridgeInstance(bot, "sync_rooms")
