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

        message = event.passthru["original_request"]["message"]
        image_id = event.passthru["original_request"]["image_id"]

        if not message:
            message = ""

        for relay_id in relay_ids:
            """XXX: media sending:

            * if media link is already available, send it immediately
              * real events from google servers will have the medialink in event.conv_event.attachment
            """

            if( hasattr(event, "conv_event")
                    and hasattr(event.conv_event, "attachments")
                    and len(event.conv_event.attachments) == 1 ):
                # catch actual events with media link, upload it to get a valid image id
                media_link = event.conv_event.attachments[0]
                logger.info("media link in original event: {}".format(media_link))

                image_id = yield from self.bot.call_shared("image_upload_single", media_link)
                message = "shared media on hangouts"

            """standard message relay"""

            formatted_message = self.format_incoming_message( message,
                                                              event.passthru["chatbridge"] )

            yield from self.bot.coro_send_message(
                relay_id,
                formatted_message,
                image_id = image_id,
                context = { "passthru": event.passthru })

    def start_listening(self, bot):
        """syncrooms do not need any special listeners"""
        pass


def _initialise(bot):
    BridgeInstance(bot, "sync_rooms")
