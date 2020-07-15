import aiohttp
import asyncio
import json
import logging
import re
import requests

from html import unescape
from urllib.parse import parse_qs
from urllib.request import urlopen

import emoji

from pyslack import SlackClient

import plugins

from sinks.base_bot_request_handler import AsyncRequestHandler

from webbridge import ( WebFramework,
                        IncomingRequestHandler,
                        FakeEvent )

logger = logging.getLogger(__name__)


_externals = { "plugin_name": "slackBasic", # same plugin name in SlackAsyncListener and BridgeInstance
               'BridgeInstance': None } # allow us to expose BridgeInstance to SlackAsyncListener

class SlackAsyncListener(AsyncRequestHandler):
    _slack_cache = {"user": {}, "channel": {}}

    def process_request(self, path, query_string, content):
        payload  = parse_qs(content)

        path = path.split("/")
        conv_id = path[1]
        if not conv_id:
            raise ValueError("conversation id must be provided in path")

        if "text" in payload:
            try:
                text = emoji.emojize(str(payload["text"][0]), use_aliases=True)
            except NameError: # emoji library likely missing
                text = str(payload["text"][0])

            if "user_name" in payload:
                if "slackbot" not in str(payload["user_name"][0]):
                    file_upload = re.search(r"<@[A-Z0-9]+\|.*?> uploaded a file: (<https?://.*?>)", text)
                    if file_upload:
                        text = re.sub(r"<@[A-Z0-9]+\|.*?> uploaded a file:", "uploaded", text)
                        # make the link clickable in hangouts
                        match = file_upload.group(1)
                        tokens = match[1:-1].rsplit("|", 1)
                        full_link = tokens[0]
                        file_name = tokens[1]
                        text = re.sub(re.escape(match), "{} with title \"{}\"".format(full_link, file_name), text)

                    text = self._slack_label_users(text)
                    text = self._slack_label_channels(text)

                    user = payload["user_name"][0] + "@slack"
                    original_message = unescape(text)

                    # cheat and use an an external variable to reach BridgeInstance

                    yield from _externals['BridgeInstance']._send_to_internal_chat(
                        conv_id,
                        original_message,
                        {   "source_user": user,
                            "source_title": False })

    def _slack_label_users(self, text):
        for fragment in re.findall("(<@([A-Z0-9]+)(\|[^>]*?)?>)", text):
            """detect and map <@Uididid> and <@Uididid|namename>"""
            full_token = fragment[0]
            id = full_token[2:-1].split("|", maxsplit=1)[0]
            username = self._slack_get_label(id, "user")
            text = text.replace(full_token, username)
        return text

    def _slack_label_channels(self, text):
        for fragment in re.findall("<#[A-Z0-9]+>", text):
            id = fragment[2:-1]
            username = self._slack_get_label(id, "channel")
            text = text.replace(fragment, username)
        return text

    def _slack_get_label(self, id, type_str):
        # hacky way to get the first token:
        slack_sink_configuration = self._bot.get_config_option('slack')
        token = slack_sink_configuration[0]["key"]

        prefix = "?"
        if type_str == "user":
            url = 'https://slack.com/api/users.info?token=' + token + '&user=' + id
            prefix = "@"
        elif type_str == "channel":
            url = 'https://slack.com/api/channels.info?token=' + token + '&channel=' + id
            prefix = "#"
        else:
            raise ValueError('unknown label type_str')

        label = "UNKNOWN"
        if id in self._slack_cache[type_str]:
            label = self._slack_cache[type_str][id]
            logger.debug("slack label resolved from cache: {} = {}".format(id, label))
        else:
            try:
                response = urlopen(url)
                json_string = str(response.read().decode('utf-8'))
                data = json.loads(json_string)
                if type_str in data:
                    label = data[type_str]["name"]
                    self._slack_cache[type_str][id] = label
                    logger.debug("slack label resolved from API: {} = {}".format(id, label))

            except Exception as e:
                logger.exception("FAILED to resolve slack label for {}".format(id))

        return prefix + label

class BridgeInstance(WebFramework):
    def setup_plugin(self):
        self.plugin_name = _externals["plugin_name"]

    def applicable_configuration(self, conv_id):
        """customised (legacy) configuration structure:

        "slack": [
            "certfile": "<location of PEM file>",
            "channel": "<hashname of slack channel>",
            "key": "<slack api key>",
            "name": "<name of server to bind for web sink>",
            "port": "<port of server to bind for web sink",
            "synced_conversations": [
                "<internal chat/group/team id>",
                "<internal chat/group/team id>",
                "<internal chat/group/team id>"
            ]
        ]

        recommendation: one hangout group in synced_conversations keys is GOOD ENOUGH"""

        self.load_configuration(self.configkey)

        applicable_configurations = []
        sinks = self.configuration
        for config in sinks:
            if conv_id in config["synced_conversations"]:
                config_clone = dict(config)
                # mutate into something closer to the webbridge standard format
                config_clone[self.configkey] = [ config_clone["channel"] ]
                config_clone["hangouts"] = config_clone["synced_conversations"]
                applicable_configurations.append({ "trigger": conv_id,
                                                   "config.json": config_clone })

        return applicable_configurations

    @asyncio.coroutine
    def _send_deferred_photo(self, image_link, relay_channels, client, slack_api_params):
        for relay_channel in relay_channels:
            logger.info("deferred post to {}".format(relay_channel))
            client.chat_post_message(relay_channel,  image_link, **slack_api_params)

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        conv_id = config["trigger"]
        relay_channels = config["config.json"][self.configkey]

        user = event.passthru["original_request"]["user"]
        message = event.passthru["original_request"]["message"]

        if not message:
            message = ""

        # XXX: rudimentary conversion of html to markdown
        message = re.sub(r"</?b>", "*", message)
        message = re.sub(r"</?i>", "_", message)
        message = re.sub(r"</?pre>", "`", message)

        bridge_user = self._get_user_details(user, { "event": event })

        try:
            client = SlackClient(config["config.json"]["key"], verify=True)
        except TypeError:
            client = SlackClient(config["config.json"]["key"])

        slack_api_params = { 'username': bridge_user["preferred_name"],
                             'icon_url': bridge_user["photo_url"] }

        if "link_names" not in config["config.json"] or config["config.json"]["link_names"]:
            slack_api_params["link_names"] = 1

        """XXX: deferred image sending

        this plugin leverages existing storage in hangouts - since there isn't a direct means
        to acquire the public url of a hangups-upload file we need to wait for other handlers to post
        the image in hangouts, which generates the public url, which we will send in a deferred post.

        handlers.image_uri_from() is packaged as a task to wait for an image link to be associated with
        an image id that this handler sees
        """

        if( "image_id" in event.passthru["original_request"]
                and event.passthru["original_request"]["image_id"] ):

            if( "conv_event" in event
                    and "attachments" in event.conv_event
                    and len(event.conv_event.attachments) == 1 ):

                message = "shared an image: {}".format(event.conv_event.attachments[0])
            else:
                # without attachments, create a deferred post until the public image url becomes available
                image_id = event.passthru["original_request"]["image_id"]

                loop = asyncio.get_event_loop()
                task = loop.create_task(
                    self.bot._handlers.image_uri_from(
                        image_id,
                        self._send_deferred_photo,
                        relay_channels,
                        client,
                        slack_api_params ))

        """standard message relay"""

        for relay_channel in relay_channels:
            client.chat_post_message(relay_channel,  message, **slack_api_params)


def _initialise(bot):
    _externals['BridgeInstance'] = BridgeInstance(bot, "slack", SlackAsyncListener)
