import asyncio
import logging
import mimetypes
import os.path
import re
import urllib.request

import emoji

from webbridge import WebFramework
import plugins

from .core import HANGOUTS, SLACK, SlackWrapper, Identities, Message
from .commands import set_bridge, run_slack_command, slack_identify, slack_sync, slack_unsync
from .parser import from_slack, from_hangups
from .utils import convert_legacy_config


logger = logging.getLogger(__name__)


class BridgeInstance(WebFramework):

    def setup_plugin(self):
        self.plugin_name = "SlackRTM"
        self.slacks = {}
        self.idents = {}

    def applicable_configuration(self, conv_id):
        """
        {
          "hangouts": ["<conv-id>", ...],
          "slackrtm": [["<team-name>", "<channel-id>"], ...]
        }
        """
        configs = []
        for sync in self.configuration["syncs"]:
            if conv_id == sync["hangout"]:
                configs.append({"trigger": conv_id,
                                "config.json": {"hangouts": [sync["hangout"]],
                                                "slackrtm": [sync["channel"]]}})
        return configs

    def map_external_uid_with_hangups_user(self, source_uid, external_context):
        team, channel = external_context["source_gid"]
        identity = self.idents[team].get(SLACK, source_uid)
        # Make sure the reverse identity holds before mapping:
        if identity and self.idents[team].get(HANGOUTS, identity) == source_uid:
            user = self.bot.get_hangups_user(identity)
            if user.definitionsource:
                logger.debug("Confirmed identity: '{}' -> '{}'".format(source_uid, identity))
                return user
        logger.debug("No identity to confirm for '{}'".format(source_uid))
        return False

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        segments = event.passthru["original_request"].get("segments")
        text = from_hangups.convert(segments)
        user = event.passthru["original_request"]["user"]
        bridge_user = self._get_user_details(user, {"event": event})
        team, channel = config["config.json"]["slackrtm"][0]
        slack = self.slacks[team]
        if bridge_user["chat_id"] == self.bot.user_self()["chat_id"]:
            # Use the bot's native Slack identity.
            kwargs = {"as_user": True}
        else:
            # Pose as the Hangouts users that sent the message.
            name = bridge_user["preferred_name"]
            if "source_title" in event.passthru["chatbridge"]:
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
            kwargs["attachments"] = attachments
        if text:
            kwargs["text"] = text
        msg = self.slacks[team].api_call("chat.postMessage",
                                         channel=channel,
                                         link_names=True,
                                         **kwargs)
        # Store the new message ID alongside the original message.
        # We'll receive an RTM event about it shortly.
        self.slacks[team].messages[channel][msg["ts"]] = event.passthru

    def start_listening(self, bot):
        for team, config in self.configuration["teams"].items():
            self.idents[team] = Identities(bot, team)
            try:
                self.slacks[team] = SlackWrapper(config["token"])
            except Exception:
                logger.exception("Failed to connect to Slack")
            else:
                plugins.start_asyncio_task(self.slacks[team].rtm_listen(self._handle_event, team))

    @asyncio.coroutine
    def _handle_event(self, event, team):
        if event["type"] == "message":
            msg = Message(event)
            if msg.hidden:
                logger.debug("Skipping Slack-only feature message of type '{}'".format(msg.type))
                return
            yield from self._handle_msg(Message(event), team)

    @asyncio.coroutine
    def _handle_msg(self, msg, team):
        if msg.channel in self.slacks[team].channels:
            yield from self._handle_channel_msg(msg, team)
        elif msg.channel in self.slacks[team].directs:
            yield from self._handle_direct_msg(msg, team)
        else:
            logger.warn("Got message '{}' from unknown channel '{}'".format(msg.id, msg.channel))

    @asyncio.coroutine
    def _handle_direct_msg(self, msg, team):
        channel = self.slacks[team].directs[msg.channel]
        user = self.slacks[team].users[channel["user"]]
        if not channel["user"] == msg.user:
            # Message wasn't sent by the user, so it was probably us.
            return
        logger.info("Got direct message '{}' from {}/{}".format(msg.ts, user["id"], user["name"]))
        run_slack_command(msg, self.slacks[team], team)

    @asyncio.coroutine
    def _handle_channel_msg(self, msg, team):
        for sync in self.configuration["syncs"]:
            team_channel = sync["channel"]
            if not [team, msg.channel] == team_channel:
                continue
            if msg.ts in self.slacks[team].messages[msg.channel]:
                # We originally received this message from the bridge.
                # Don't relay it back, just remove the original from our cache.
                del self.slacks[team].messages[msg.channel][msg.ts]
            elif msg.file:
                # Create a background task to upload the attached image to Hangouts.
                asyncio.get_event_loop().create_task(self._relay_msg_image(msg, sync["hangout"], team))
            else:
                # Relay the message over to Hangouts.
                yield from self._relay_msg(msg, sync["hangout"], team)

    @asyncio.coroutine
    def _relay_msg_image(self, msg, conv_id, team):
        filename = os.path.basename(msg.file)
        logger.info("Uploading Slack image '{}' to Hangouts".format(filename))
        # Retrieve the image content from Slack.
        request = urllib.request.Request(msg.file)
        request.add_header("Authorization", "Bearer {}".format(config["token"]))
        response = urllib.request.urlopen(request)
        name_ext = "." + filename.rsplit(".", 1).pop().lower()
        # Check the file extension matches the MIME type.
        mime_type = response.info().get_content_type()
        mime_exts = mimetypes.guess_all_extensions(mime_type)
        if name_ext.lower() not in [ext.lower() for ext in mime_exts]:
            logger.debug("MIME '{}' does not match extension '{}', changing to {}".format(mime_type, name_ext, mime_exts[0]))
            filename = "{}{}".format(filename, mime_exts[0])
        image_id = yield from self.bot._client.upload_image(response, filename=filename)
        yield from self._relay_msg(msg, conv_id, team, image_id)

    @asyncio.coroutine
    def _relay_msg(self, msg, conv_id, team, image_id=None):
        try:
            user = self.slacks[team].users[msg.user]["name"]
        except KeyError:
            # Bot message with no corresponding Slack user.
            user = msg.user_name
        try:
            source = self.slacks[team].channels[msg.channel]["name"]
        except KeyError:
            source = team
        yield from self._send_to_internal_chat(conv_id,
                                               from_slack.convert(emoji.emojize(msg.text, use_aliases=True)),
                                               {"source_user": user,
                                                "source_uid": msg.user,
                                                "source_gid": [team, msg.channel],
                                                "source_title": source,
                                                "source_edited": msg.edited,
                                                "source_action": msg.action},
                                               image_id=image_id)


def _initialise(bot):
    convert_legacy_config(bot)
    plugins.register_user_command(["slack_identify"])
    plugins.register_admin_command(["slack_sync", "slack_unsync"])
    set_bridge(BridgeInstance(bot, "slackrtm"))
