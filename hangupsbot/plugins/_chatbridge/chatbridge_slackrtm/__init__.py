import asyncio
import logging
import mimetypes
import os.path
import re
import urllib.request

import emoji
from slackclient import SlackClient

from webbridge import WebFramework
import plugins

from plugins.slackrtm.parsers import slack_markdown_to_hangups, hangups_markdown_to_slack

from .utils import convert_legacy_config


logger = logging.getLogger(__name__)


class SlackMsg(object):

    def __init__(self, event):
        self.event = event
        self.ts = self.event["ts"]
        self.channel = self.event.get("channel") or self.event.get("group")
        self.edited = self.event.get("subtype") == "message_changed"
        self.action = False
        self.msg = self.event["message"] if self.edited else self.event
        self.user = self.msg.get("user")
        self.user_name = None
        self.text = self.msg.get("text")
        self.file = None
        self.type = self.msg.get("subtype")
        if self.type == "bot_message":
            self.user_name = self.msg.get("username")
        elif self.type == "file_comment":
            self.action = True
            self.user = self.msg["comment"]["user"]
        elif self.type in ("file_share", "file_mention") and "file" in self.msg:
            self.action = True
            if "url_private_download" in self.msg["file"]:
                self.file = self.msg["file"]["url_private_download"]
        elif self.type in ("channel_name", "channel_purpose", "channel_topic", "channel_join", "channel_part",
                         "group_name", "group_purpose", "group_topic", "group_join", "group_part", "me_message"):
            self.action = True
        elif self.type in ("channel_archive", "channel_unarchive", "group_archive", "group_unarchive"):
            logger.warn("Channel is being (un)archived")
        if self.action:
            # Strip own username from the start of the message.
            self.text = re.sub(r"^<@{}|.*?> ".format(self.user), "", self.text)


class BridgeInstance(WebFramework):

    def setup_plugin(self):
        self.plugin_name = "SlackRTM"
        self.slacks = {}
        self.users = {}
        self.channels = {}
        self.msg_cache = {}

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

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        text = event.passthru["original_request"]["message"]
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
            kwargs["text"] = hangups_markdown_to_slack(text)
        msg = self._api_call(team, "chat.postMessage",
                             channel=channel, link_names=True, **kwargs)
        # Store the new message ID alongside the original message.
        # We'll receive an RTM event about it shortly.
        self.msg_cache[channel][msg["ts"]] = event.passthru

    def start_listening(self, bot):
        for team, config in self.configuration["teams"].items():
            plugins.start_asyncio_task(self._rtm_listen, team, config)

    def _api_call(self, team, method, *args, **kwargs):
        resp = self.slacks[team].api_call(method, *args, **kwargs)
        if not resp["ok"]:
            logger.error("Error from Slack '{}' API call: {}".format(method, resp["error"]))
            return
        if "warning" in resp:
            logger.warn("Warning from Slack '{}' API call: {}".format(method, resp["warning"]))
        return resp

    @asyncio.coroutine
    def _rtm_listen(self, bot, team, config):
        logger.info("Starting RTM session for team '{}'".format(team))
        slack = SlackClient(config["token"])
        self.slacks[team] = slack
        for sync in self.configuration["syncs"]:
            team, channel = sync["channel"]
            if channel not in self.msg_cache:
                self.msg_cache[channel] = {}
        if not slack.rtm_connect():
            logger.error("Failed to connect to RTM")
            return
        # Cache an initial list of users and channels.
        self.users[team] = {u["id"]: u for u in self._api_call(team, "users.list")["members"]}
        self.channels[team] = {c["id"]: c for c in self._api_call(team, "channels.list")["channels"] +
                                                   self._api_call(team, "groups.list")["groups"]}
        while True:
            events = slack.rtm_read()
            if not events:
                yield from asyncio.sleep(0.5)
                continue
            for event in events:
                if event["type"] == "message":
                    try:
                        yield from self._handle_msg(event, team, config)
                    except Exception as e:
                        logger.exception("Failed to handle message")
                elif event["type"] in ("team_join", "user_change"):
                    # A user changed, update our cache.
                    user = event["user"]
                    self.users[team][user["id"]] = user

    @asyncio.coroutine
    def _handle_msg(self, event, team, config):
        msg = SlackMsg(event)
        if not msg.edited and event.get("hidden") or msg.type in ("pinned_item", "unpinned_item", "channel_unarchive", "group_unarchive"):
            logger.debug("Skipping Slack-only feature message of type '{}'".format(msg.type))
            return
        for sync in self.configuration["syncs"]:
            team_channel = sync["channel"]
            if not [team, msg.channel] == team_channel:
                continue
            cache = self.msg_cache[msg.channel]
            passthru = cache.get(msg.ts)
            if passthru:
                # We originally received this message from the bridge.
                # Don't relay it back, just remove the original from our cache.
                del cache[msg.ts]
            elif msg.file:
                # Create a background task to upload the attached image to Hangouts.
                asyncio.get_event_loop().create_task(self._relay_msg_image(msg, sync["hangout"], team, config))
            else:
                # Relay the message over to Hangouts.
                yield from self._relay_msg(msg, sync["hangout"], team, config)
        self.slacks[team].api_call("channels.mark", channel=msg.channel, ts=msg.ts)

    @asyncio.coroutine
    def _relay_msg_image(self, msg, conv_id, team, config):
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
        yield from self._relay_msg(msg, conv_id, team, config, image_id)

    @asyncio.coroutine
    def _relay_msg(self, msg, conv_id, team, config, image_id=None):
        try:
            user = self.users[team][msg.user]["name"]
        except KeyError:
            # Bot message with no corresponding Slack user.
            user = msg.user_name
        try:
            source = self.channels[team][msg.channel]["name"]
        except KeyError:
            source = team
        yield from self._send_to_internal_chat(conv_id,
                                               slack_markdown_to_hangups(emoji.emojize(msg.text, use_aliases=True)),
                                               {"source_user": user,
                                                "source_uid": msg.user,
                                                "source_gid": msg.channel,
                                                "source_title": source,
                                                "source_edited": msg.edited,
                                                "source_action": msg.action},
                                               image_id=image_id)


def _initialise(bot):
    convert_legacy_config(bot)
    BridgeInstance(bot, "slackrtm")
