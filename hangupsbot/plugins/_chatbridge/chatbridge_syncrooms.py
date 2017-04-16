import aiohttp
import asyncio
import json
import logging
import requests

from hangups import ChatMessageEvent

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

        is_action = event.passthru["chatbridge"].get("source_action")

        if not message:
            message = ""

        if (hasattr(event, "conv_event") and isinstance(event.conv_event, ChatMessageEvent) and
                any(a.type == 4 for a in event.conv_event._event.chat_message.annotation)):
            # This is a /me message sent from desktop Hangouts.
            is_action = True
            # The user's first name prefixes the message, so try to strip that.
            user_id = event.passthru["chatbridge"].get("source_user")
            user = self._get_user_details(user_id)
            name = user.get("full_name")
            if name:
                # We don't have a clear-cut first name, so try to match parts of names.
                # Try the full name first, then split successive words off the end.
                parts = name.split()
                for pos in range(len(parts), 0, -1):
                    sub_name = " ".join(parts[:pos])
                    if message.startswith(sub_name):
                        message = message[len(sub_name) + 1:]
                        break
                else:
                    # Couldn't match the user's name to the message text.
                    # Possible mismatch between permamem and Hangouts?
                    logger.warn("/me message: couldn't match name '{}' ({}) with message text"
                                .format(name, user_id))

        attach = None
        if hasattr(event, "conv_event") and getattr(event.conv_event, "attachments"):
            attach = event.conv_event.attachments[0]
            if attach == message:
                # Message consists solely of the attachment URL, no need to send that.
                message = "shared an image"
                is_action = True
            elif attach in message:
                # Message includes some text too, strip the attachment URL from the end if present.
                message = message.replace("\n{}".format(attach), "")

        event.passthru["chatbridge"]["source_action"] = is_action

        for relay_id in relay_ids:
            """XXX: media sending:

            * if media link is already available, send it immediately
              * real events from google servers will have the medialink in event.conv_event.attachment
            """

            # catch actual events with media link, upload it to get a valid image id
            if attach:
                logger.info("media link in original event: {}".format(attach))
                image_id = yield from self.bot.call_shared("image_upload_single", attach)

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
