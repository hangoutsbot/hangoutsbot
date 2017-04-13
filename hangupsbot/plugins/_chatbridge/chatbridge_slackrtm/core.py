import asyncio
import logging
import re

from slackclient import SlackClient


logger = logging.getLogger(__name__)


class SlackAPIError(Exception): pass


class SlackWrapper(SlackClient):
    """
    An extension of SlackClient to provide user/channel caches, and automatically start RTM.
    """

    def __init__(self, token):
        self.slack = super().__init__(token)
        if not self.rtm_connect():
            raise SlackAPIError("Failed to start RTM session")
        # Ideally SlackClient would give us this information from RTM init...
        self.users = {}
        self.channels = {}
        self.directs = {}
        self.messages = {}
        for user in self.api_call("users.list", "members"):
            self.cache_user(user)
        logger.debug("Users ({}): {}".format(len(self.users), ", ".join(self.users.keys())))
        for channel in (self.api_call("channels.list", "channels") +
                        self.api_call("groups.list", "groups")):
            self.cache_channel(channel)
        logger.debug("Channels ({}): {}".format(len(self.channels), ", ".join(self.channels.keys())))
        for direct in self.api_call("im.list", "ims"):
            self.cache_direct(direct)
        logger.debug("Directs ({}): {}".format(len(self.directs), ", ".join(self.directs.keys())))

    def cache_user(self, user):
        self.users[user["id"]] = user

    def cache_channel(self, channel):
        self.channels[channel["id"]] = channel
        self.messages[channel["id"]] = {}

    def cache_direct(self, direct):
        self.directs[direct["id"]] = direct

    def api_call(self, method, key=None, *args, **kwargs):
        """
        Make a HTTP API call.  Throws SlackAPIError on failure.
        """
        logger.debug("Calling Slack API '{}'".format(method))
        resp = super().api_call(method, *args, **kwargs)
        if not resp["ok"]:
            raise SlackAPIError(resp["error"])
        return resp[key] if key else resp

    @asyncio.coroutine
    def rtm_listen(self, callback, *args, **kwargs):
        """
        Listen over RTM forever, maintaining the cache if we find new users or channels.
        """
        while True:
            events = self.rtm_read()
            if not events:
                yield from asyncio.sleep(0.5)
                continue
            for event in events:
                logger.debug("Received a '{}' event".format(event["type"]))
                if event["type"] in ("team_join", "user_change"):
                    # A user changed, update our cache.
                    self.cache_user(event["user"])
                elif event["type"] in ("channel_joined", "group_joined"):
                    # A group or channel appeared, add to our cache.
                    self.cache_channel(event["channel"])
                elif event["type"] == "im_created":
                    # A DM appeared, add to our cache.
                    self.cache_direct(event["channel"])
                try:
                    yield from callback(event, *args, **kwargs)
                except Exception:
                    logger.exception("Failed to handle event")


class Identities(object):

    def __init__(self, bot, team):
        self.bot = bot
        self.team = team
        try:
            idents = self.bot.memory.get_by_path(["slackrtm", self.team, "identities"])
        except (KeyError, TypeError):
            self.hangouts = {}
            self.slack = {}
        else:
            self.hangouts = idents.get("hangouts") or {}
            self.slack = idents.get("slack") or {}

    def get_hangouts(self, user):
        return self.hangouts.get(user)

    def get_slack(self, user):
        return self.slack.get(user)

    def add_hangouts(self, user, mapping):
        self.hangouts[user] = mapping
        self.save()

    def add_slack(self, user, mapping):
        self.slack[user] = mapping
        self.save()

    def del_hangouts(self, user):
        del self.hangouts[user]
        self.save()

    def del_slack(self, user):
        del self.slack[user]
        self.save()

    def save(self):
        self.bot.memory.set_by_path(["slackrtm", self.team, "identities"],
                                    {"hangouts": self.hangouts, "slack": self.slack})


class Message(object):

    def __init__(self, event):
        self.event = event
        self.ts = self.event["ts"]
        self.channel = self.event.get("channel") or self.event.get("group")
        self.hidden = False
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
        if self.event.get("hidden") and not self.edited:
            self.hidden = True
        elif self.type in ("pinned_item", "unpinned_item", "channel_unarchive", "group_unarchive"):
            self.hidden = True
        if self.action:
            # Strip own username from the start of the message.
            self.text = re.sub(r"^<@{}|.*?> ".format(self.user), "", self.text)
