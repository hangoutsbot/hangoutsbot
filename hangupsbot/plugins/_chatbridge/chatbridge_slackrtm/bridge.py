import asyncio
from collections import defaultdict
from io import BytesIO
import json
import logging
import mimetypes
import os.path
import re
import urllib.parse

from hangups import hangouts_pb2
import emoji

from webbridge import WebFramework, FakeEvent
import plugins

from .core import HANGOUTS, SLACK, Base, Message
from .parser import from_slack, from_hangups


logger = logging.getLogger(__name__)


class BridgeInstance(WebFramework):

    def __init__(self, bot, configkey, sync):
        meta = {"module": "chatbridge_slackrtm",
                "module.path": "plugins._chatbridge.chatbridge_slackrtm"}
        meta.update(sync)
        super().__init__(bot, configkey, extra_metadata=meta)
        self.sync = sync
        self.team, self.channel = sync["channel"]
        self.hangout = sync["hangout"]

    def setup_plugin(self):
        self.plugin_name = "SlackRTM"
        self.messages = {}

    def applicable_configuration(self, conv_id):
        """
        {
          "hangouts": ["<conv-id>"],
          "slackrtm": [["<team-name>", "<channel-id>"]]
        }
        """
        if not conv_id == self.hangout:
            return []
        return [{"trigger": conv_id,
                 "config.json": {"hangouts": [self.hangout],
                                 "slackrtm": [[self.team, self.channel]]}}]

    def map_external_uid_with_hangups_user(self, source_uid, external_context):
        identity = Base.idents[self.team].get(SLACK, source_uid)
        # Make sure the reverse identity holds before mapping:
        if identity and Base.idents[self.team].get(HANGOUTS, identity) == source_uid:
            user = self.bot.get_hangups_user(identity)
            if user.definitionsource:
                logger.debug("Confirmed identity: '{}' -> '{}'".format(source_uid, identity))
                return user
        logger.debug("No identity to confirm for '{}'".format(source_uid))
        return False

    @asyncio.coroutine
    def send_to_external_1to1(self, user_id, message):
        slack = Base.slacks[self.team]
        channel = yield from slack.dm(user_id)
        yield from slack.msg(channel=channel, as_user=True, text=message)

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        if event.passthru["original_request"].get("image_id"):
            # We need to resolve this ID to an image before we process it.
            handler = self.bot._handlers.image_uri_from(event.passthru["original_request"]["image_id"],
                                                        self._retry_external_with_image, config, event)
            asyncio.get_event_loop().create_task(handler)
            return
        segments = event.passthru["original_request"].get("segments")
        message = event.passthru["original_request"].get("message")
        text = from_hangups.convert(segments or message, Base.slacks[self.team])
        user = event.passthru["original_request"]["user"]
        bridge_user = self._get_user_details(user, {"event": event})
        if bridge_user["chat_id"] == self.bot.user_self()["chat_id"]:
            # Use the bot's native Slack identity.
            kwargs = {"as_user": True}
        else:
            # Pose as the Hangouts users that sent the message.
            name = bridge_user["preferred_name"]
            hide_preference = self.bot.config.get_option("chatbridge_hide_source")
            if "source_title" in event.passthru["chatbridge"] and not hide_preference:
                name = "{} ({})".format(name, event.passthru["chatbridge"]["source_title"])
            kwargs = {"username": name,
                      "icon_url": bridge_user["photo_url"]}
        attachments = []
        # Display images in attachment form.
        # Slack will also show a filename and size under the message text.
        for attach in event.passthru["original_request"].get("attachments") or []:
            # Filenames in Hangouts URLs are double-percent-encoded.
            filename = urllib.parse.unquote(urllib.parse.unquote(os.path.basename(attach))).replace("+", " ")
            attachments.append({"fallback": attach,
                                "text": filename,
                                "image_url": attach})
            if attach == text:
                # Message consists solely of the attachment URL, no need to send that.
                text = None
            elif attach in text:
                # Message includes some text too, strip the attachment URL from the end if present.
                text = text.replace("\n{}".format(attach), "")
        if attachments:
            kwargs["attachments"] = json.dumps(attachments)
        if text:
            kwargs["text"] = text
        msg = yield from Base.slacks[self.team].msg(channel=self.channel, link_names=True, **kwargs)
        # Store the new message ID alongside the original message.
        # We'll receive an RTM event about it shortly.
        self.messages[msg["ts"]] = event.passthru

    @asyncio.coroutine
    def _retry_external_with_image(self, image_url, config, event):
        # Replace the image ID with the attachment URL.
        if event.passthru["original_request"].get("attachments"):
            event.passthru["original_request"]["attachments"].append(image_url)
        else:
            event.passthru["original_request"]["attachments"] = [image_url]
        event.passthru["original_request"]["image_id"] = None
        yield from self._send_to_external_chat(config, event)

    @asyncio.coroutine
    def _handle_channel_msg(self, msg):
        if not msg.channel == self.channel:
            return
        if msg.ts in self.messages:
            # We originally received this message from the bridge.
            # Don't relay it back, just remove the original from our cache.
            del self.messages[msg.ts]
        elif msg.file:
            # Create a background task to upload the attached image to Hangouts.
            asyncio.get_event_loop().create_task(self._relay_msg_image(msg, self.hangout))
        else:
            # Relay the message over to Hangouts.
            yield from self._relay_msg(msg, self.hangout)

    @asyncio.coroutine
    def _relay_msg_image(self, msg, conv_id):
        filename = os.path.basename(msg.file)
        logger.info("Uploading Slack image '{}' to Hangouts - {}".format(filename, json.dumps(msg.file)))
        for retry_count in range(3):
            try:
                logger.debug("Attempt {} at downloading file".format(retry_count+1))
                # Retrieve the image content from Slack.
                resp = yield from Base.slacks[self.team].sess.get(msg.file,
                                                                  headers={"Authorization": "Bearer {}".format(
                                                                      Base.slacks[self.team].token)})
                # logger.debug(resp)
                name_ext = "." + filename.rsplit(".", 1).pop().lower()
                # Check the file extension matches the MIME type.
                mime_type = resp.content_type
                mime_exts = mimetypes.guess_all_extensions(mime_type)
                if name_ext.lower() not in [ext.lower() for ext in mime_exts]:
                    raise ValueError("MIME '{}' does not match extension '{}', we probably didn't get the right file." +
                                     " Attempt [{}/3]"
                                     .format(mime_type, name_ext, retry_count+1))
                image = yield from resp.read()
                # logger.debug(json.dumps(image))
                image_id = yield from self.bot._client.upload_image(BytesIO(image), filename=filename)
                yield from self._relay_msg(msg, conv_id, image_id)
                break
            except ValueError as err:
                logger.error(err)
                yield from asyncio.sleep(2)

    @asyncio.coroutine
    def _relay_msg(self, msg, conv_id, image_id=None):
        try:
            user = Base.slacks[self.team].users[msg.user]["name"]
        except KeyError:
            # Bot message with no corresponding Slack user.
            user = msg.user_name
        try:
            source = Base.slacks[self.team].channels[msg.channel]["name"]
        except KeyError:
            source = self.team
        yield from self._send_to_internal_chat(conv_id,
                                               from_slack.convert(emoji.emojize(msg.text, use_aliases=True),
                                                                  Base.slacks[self.team]),
                                               {"source_user": user,
                                                "source_uid": msg.user,
                                                "source_title": source,
                                                "source_edited": msg.edited,
                                                "source_action": msg.action},
                                               image_id=image_id)


@asyncio.coroutine
def on_membership_change(bot, event, command=""):
    root = bot.get_config_option("slackrtm") or {}
    syncs = [sync["channel"] for sync in root.get("syncs", []) if sync["hangout"] == event.conv_id]
    if not syncs:
        return
    join = event.conv_event.type_ == hangouts_pb2.MEMBERSHIP_CHANGE_TYPE_JOIN
    users = [event.conv.get_user(user_id) for user_id in event.conv_event.participant_ids]
    if users == [event.user]:
        text = "{} the hangout".format("joined" if join else "left")
    else:
        text = "{} {} {} the hangout".format("added" if join else "removed",
                                             ", ".join(user.full_name for user in users),
                                             "to" if join else "from")
    for team, channel in syncs:
        for bridge in Base.bridges[team]:
            if bridge.channel == channel:
                config = bridge.applicable_configuration(event.conv_id)
                passthru = {"original_request": {"message": text,
                                                 "image_id": None,
                                                 "segments": None,
                                                 "user": event.user},
                            "chatbridge": {"source_title": bot.conversations.get_name(event.conv_id),
                                           "source_user": event.user,
                                           "source_uid": event.user.id_.chat_id,
                                           "source_gid": event.conv_id,
                                           "source_action": True,
                                           "source_edit": False,
                                           "source_plugin": bridge.plugin_name}}
                fake = FakeEvent(text, event.user, passthru, event.conv_id)
                yield from bridge._send_to_external_chat(config, fake)
