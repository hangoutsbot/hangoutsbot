import aiohttp
import asyncio
from collections import defaultdict
import logging
import re

from slackclient import SlackClient


logger = logging.getLogger(__name__)


HANGOUTS = "Hangouts"
SLACK = "Slack"

def inv(source):
    return HANGOUTS if source == SLACK else SLACK


class Base(object):
    """
    Container for bridge and Slack instances.
    """

    bot = None
    bridges = defaultdict(list)
    slacks = {}
    idents = {}

    @classmethod
    def add_slack(cls, slack):
        cls.slacks[slack.name] = slack
        cls.idents[slack.name] = Identities(cls.bot, slack.name)

    @classmethod
    def remove_slack(cls, slack):
        slack.stop()
        for bridge in list(Base.bridges[slack.name]):
            Base.remove_bridge(bridge)
        del cls.idents[slack.name]
        del cls.slacks[slack.name]

    @classmethod
    def add_bridge(cls, bridge):
        logger.info("Registering new bridge: {} {} <--> {}".format(bridge.team, bridge.channel, bridge.hangout))
        Base.bridges[bridge.team].append(bridge)
        Base.slacks[bridge.team].callbacks.append(bridge._handle_channel_msg)

    @classmethod
    def remove_bridge(cls, bridge):
        logger.info("Unregistering bridge: {} {} <-/-> {}".format(bridge.team, bridge.channel, bridge.hangout))
        Base.bridges[bridge.team].remove(bridge)
        Base.slacks[bridge.team].callbacks.remove(bridge._handle_channel_msg)
        bridge.close()


class SlackAPIError(Exception): pass


class Slack(object):
    """
    A tiny async Slack client for the RTM APIs.
    """

    def __init__(self, name, token):
        self.name = name
        self.token = token
        self.sess = aiohttp.ClientSession()
        self.team = self.users = self.channels = self.directs = None
        # When we send messages asynchronously, we'll receive an RTM event before the HTTP request
        # returns. This lock will block event parsing whilst we're sending, to make sure the caller
        # can finish processing the new message (e.g. storing the ID) before receiving the event.
        self.lock = asyncio.BoundedSemaphore()
        self.callbacks = []
        # Internal tracking of the RTM task, used to cancel on plugin unload.
        self._task = None

    @asyncio.coroutine
    def dm(self, user_id):
        resp = yield from self.sess.post("https://slack.com/api/im.open",
                                         data={"token": self.token, "user": user_id})
        json = yield from resp.json()
        if not json["ok"]:
            raise SlackAPIError(json["error"])
        return json["channel"]["id"]

    @asyncio.coroutine
    def msg(self, **kwargs):
        logger.debug("Sending message")
        with (yield from self.lock):
            # Block event processing whilst we wait for the message to go through. Processing will
            # resume once the caller yields or returns.
            resp = yield from self.sess.post("https://slack.com/api/chat.postMessage",
                                             data=dict(kwargs, token=self.token))
            json = yield from resp.json()
        if not json["ok"]:
            raise SlackAPIError(json["error"])
        return json

    @asyncio.coroutine
    def rtm(self):
        logger.debug("Requesting RTM session")
        resp = yield from self.sess.post("https://slack.com/api/rtm.start",
                                         data={"token": self.token})
        json = yield from resp.json()
        if not json["ok"]:
            raise SlackAPIError(json["error"])
        # Cache useful information about users and channels, to save on queries later.
        self.team = json["team"]
        self.users = {u["id"]: u for u in json["users"]}
        logger.debug("Users ({}): {}".format(len(self.users), self.users.keys()))
        self.channels = {c["id"]: c for c in json["channels"] + json["groups"]}
        logger.debug("Channels ({}): {}".format(len(self.channels), self.channels.keys()))
        self.directs = {c["id"]: c for c in json["ims"]}
        logger.debug("Directs ({}): {}".format(len(self.directs), self.directs.keys()))
        sock = yield from self.sess.ws_connect(json["url"], heartbeat=30.0)
        logger.debug("Connected to websocket")
        while True:
            event = yield from sock.receive_json()
            if "type" not in event:
                logger.warn("Received strange message with no type")
                continue
            logger.debug("Received a '{}' event, ts = {}".format(event["type"], event.get("ts")))
            if event["type"] in ("team_join", "user_change"):
                # A user appears or changed, update our cache.
                self.users[event["user"]["id"]] = event["user"]
            elif event["type"] in ("channel_joined", "group_joined"):
                # A group or channel appeared, add to our cache.
                self.channels[event["channel"]["id"]] = event["channel"]
            elif event["type"] == "im_created":
                # A DM appeared, add to our cache.
                self.directs[event["channel"]["id"]] = event["channel"]
            elif event["type"] == "message":
                with (yield from self.lock):
                    # No critical section here, just wait for any pending messages to be sent.
                    pass
                msg = Message(event)
                if msg.hidden:
                    logger.debug("Skipping Slack-only feature message of type '{}'".format(msg.type))
                    continue
                if msg.edited and not msg.edited == msg.user:
                    logger.debug("Skipping message edited by non-author (possible link unfurl)".format(msg.type))
                    continue
                if msg.channel in self.channels:
                    logger.info("Got channel message '{}' in {} from {}".format(msg.ts, msg.channel, msg.user))
                    # Message received in a channel.
                    for callback in self.callbacks:
                        try:
                            yield from callback(msg)
                        except Exception:
                            logger.exception("Failed callback for event")
                elif msg.channel in self.directs:
                    logger.info("Got direct message '{}' from {}".format(msg.ts, msg.user))
                    # Private message to the bot.
                    channel = self.directs[msg.channel]
                    user = self.users[channel["user"]]
                    if not channel["user"] == msg.user:
                        # Message wasn't sent by the user, so it was probably us.
                        continue
                    # XXX: Circular dependency on core.*, commands.run_slack_command.
                    from .commands import run_slack_command
                    yield from run_slack_command(msg, self)
                else:
                    logger.warn("Got message '{}' from unknown channel '{}'".format(msg.ts, msg.channel))

    @asyncio.coroutine
    def loop(self):
        while True:
            try:
                yield from self.rtm()
            except asyncio.CancelledError:
                logger.debug("Unloading or cancelled")
                return
            except Exception:
                logger.exception("Disconnected from Slack")
            logger.debug("Waiting 5 seconds to reconnect")
            yield from asyncio.sleep(5)

    def start(self):
        if not self._task:
            self._task = asyncio.ensure_future(self.loop())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None


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

    def __call__(self, key):
        return {HANGOUTS: self.hangouts, SLACK: self.slack}[key]

    def get(self, key, user):
        return self(key).get(user)

    def add(self, key, user, mapping):
        self(key)[user] = mapping
        self.save()

    def remove(self, key, user):
        del self(key)[user]
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
        elif self.type in ("channel_name", "channel_purpose", "channel_topic", "channel_join", "channel_part",
                           "group_name", "group_purpose", "group_topic", "group_join", "group_part", "me_message"):
            self.action = True
        elif self.type in ("channel_archive", "channel_unarchive", "group_archive", "group_unarchive"):
            logger.warn("Channel is being (un)archived")
        if self.msg.get("files") and "url_private_download" in self.msg["files"][0]:
            self.file = self.msg["files"][0]["url_private_download"]
            if not self.text:
                self.action = True
                self.text = "uploaded a file"
                if self.msg["files"][0].get("title"):
                    self.text += ": {}".format(self.msg["files"][0]["title"])
        if self.msg.get("attachments"):
            # Take a plain text representation of each attachment, if available.
            attaches = [attach.get("fallback", attach.get("text")) for attach in self.msg["attachments"]]
            self.text = "\n".join(filter(None, [self.text] + attaches))
        if self.edited and self.msg.get("edited", {}).get("user"):
            # Store the editing user's ID if known.
            self.edited = self.msg["edited"]["user"]
        if self.event.get("hidden") and not self.edited:
            self.hidden = True
        elif self.event.get("is_ephemeral"):
            self.hidden = True
        elif self.type in ("pinned_item", "unpinned_item", "channel_unarchive", "group_unarchive"):
            self.hidden = True
        if self.action:
            # Strip own username from the start of the message.
            self.text = re.sub(r"^<@{}|.*?> ".format(self.user), "", self.text)
