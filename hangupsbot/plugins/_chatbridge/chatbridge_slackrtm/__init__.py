import asyncio
import logging
import mimetypes
import os.path
import urllib.request

from slackclient import SlackClient

from webbridge import WebFramework
import plugins


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
        self.text = self.msg.get("text")
        self.file = None
        subtype = self.msg.get("subtype")
        if subtype == "file_comment":
            self.action = True
            self.user = self.msg["comment"]["user"]
        elif subtype in ("file_share", "file_mention") and "file" in self.msg:
            self.action = True
            if "url_private_download" in self.msg["file"]:
                self.file = self.msg["file"]["url_private_download"]
        elif subtype in ("channel_name", "channel_purpose", "channel_topic", "channel_join", "channel_part",
                         "group_name", "group_purpose", "group_topic", "group_join", "group_part", "me_message"):
            self.action = True
        elif subtype in ("channel_archive", "channel_unarchive", "group_archive", "group_unarchive"):
            logger.warn("Channel is being (un)archived")
        elif self.msg.get("hidden") or subtype in ("pinned_item", "unpinned_item", "channel_unarchive", "group_unarchive"):
            logger.debug("Skipping Slack-only feature message of type: {}".format(subtype))


class BridgeInstance(WebFramework):

    def setup_plugin(self):
        self.plugin_name = "SlackRTM"
        self.slacks = {}
        self.users = {}
        self.msg_cache = {}

    def applicable_configuration(self, conv_id):
        configs = []
        for sync in self.configuration["syncs"]:
            if conv_id in sync["hangouts"]:
                configs.append({"trigger": conv_id, "config.json": sync})
        return configs

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        for channel in config["config.json"]["slack"]:
            slack = self.slacks[channel["team"]]
            user = event.passthru["original_request"]["user"]
            bridge_user = self._get_user_details(user, {"event": event})
            if bridge_user["chat_id"] == self.bot.user_self()["chat_id"]:
                identity = {"as_user": True}
            else:
                identity = {"username": bridge_user["preferred_name"],
                            "icon_url": bridge_user["photo_url"]}
            message = event.passthru["original_request"]["message"]
            msg = slack.api_call("chat.postMessage",
                                 channel=channel["channel"],
                                 text=message,
                                 link_names=True,
                                 **identity)
            self.msg_cache[channel["channel"]].add(msg["ts"])

    def start_listening(self, bot):
        for team, config in self.configuration["teams"].items():
            plugins.start_asyncio_task(self._rtm_listen, team, config)

    @asyncio.coroutine
    def _rtm_listen(self, bot, team, config):
        logger.info("Starting RTM session for team: {}".format(team))
        slack = SlackClient(config["token"])
        self.slacks[team] = slack
        for sync in self.configuration["syncs"]:
            for channel in sync["slack"]:
                if not channel["channel"] in self.msg_cache:
                    self.msg_cache[channel["channel"]] = set()
        slack.rtm_connect()
        self.users[team] = {u["id"]: u for u in slack.api_call("users.list")["members"]}
        while True:
            events = slack.rtm_read()
            if not events:
                yield from asyncio.sleep(0.5)
                continue
            for event in events:
                if event["type"] == "message":
                    yield from self._handle_msg(event, team, config)
                elif event["type"] in ("team_join", "user_change"):
                    user = event["user"]
                    self.users[team][user["id"]] = user

    @asyncio.coroutine
    def _handle_msg(self, event, team, config):
        msg = SlackMsg(event)
        user = self.users[team][msg.user]
        for sync in self.configuration["syncs"]:
            for channel in sync["slack"]:
                if msg.channel == channel["channel"] and team == channel["team"]:
                    cache = self.msg_cache[channel["channel"]]
                    if msg.ts in cache:
                        cache.remove(msg.ts)
                        continue
                    for conv_id in sync["hangouts"]:
                        if msg.file:
                            asyncio.get_event_loop().create_task(self._relay_msg_image(msg, conv_id, team, config))
                        else:
                            yield from self._relay_msg(msg, conv_id, team, config)

    @asyncio.coroutine
    def _relay_msg_image(self, msg, conv_id, team, config):
        filename = os.path.basename(msg.file)
        request = urllib.request.Request(msg.file)
        request.add_header("Authorization", "Bearer {}".format(config["token"]))
        response = urllib.request.urlopen(request)
        name_ext = "." + filename.rsplit(".", 1).pop().lower()
        mime_type = response.info().get_content_type()
        mime_exts = mimetypes.guess_all_extensions(mime_type)
        if name_ext.lower() not in [ext.lower() for ext in mime_exts]:
            logger.debug("MIME '{}' does not match extension '{}', changing to {}".format(mime_type, name_ext, mime_exts[0]))
            filename = "{}{}".format(filename, mime_exts[0])
        image_id = yield from self.bot._client.upload_image(response, filename=filename)
        yield from self._relay_msg(msg, conv_id, team, config, image_id)

    @asyncio.coroutine
    def _relay_msg(self, msg, conv_id, team, config, image_id=None):
        yield from self._send_to_internal_chat(conv_id, msg.text,
                                               {"source_user": self.users[team][msg.user]["name"],
                                                "source_uid": msg.user,
                                                "source_gid": msg.channel,
                                                "source_title": msg.channel,
                                                "source_edited": msg.edited,
                                                "source_action": msg.action},
                                               image_id=image_id)


def _initialise(bot):
    BridgeInstance(bot, "slackrtm")
