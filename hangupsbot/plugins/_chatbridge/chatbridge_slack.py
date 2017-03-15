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
                    text = self._slack_label_users(text)
                    text = self._slack_label_channels(text)

                    user = payload["user_name"][0] + "@slack"
                    original_message = unescape(text)
                    message = "{}: {}".format(user, original_message)

                    # cheat and use an an external variable to reach BridgeInstance

                    yield from _externals['BridgeInstance']._send_to_internal_chat(
                        conv_id,
                        FakeEvent(
                            text = message,
                            user = user,
                            passthru = {
                                "original_request": {
                                    "message": original_message,
                                    "image_id": None,
                                    "segments": None,
                                    "user": user },
                                "norelay": [ _externals["plugin_name"] ] }))

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
    def _send_to_external_chat(self, config, event):
        conv_id = config["trigger"]
        relay_channels = config["config.json"][self.configkey]

        user = event.passthru["original_request"]["user"]
        message = event.passthru["original_request"]["message"]

        preferred_name, nickname, full_name, photo_url = _externals['BridgeInstance']._standardise_bridge_user_details(user)

        try:
            client = SlackClient(config["config.json"]["key"], verify=True)
        except TypeError:
            client = SlackClient(config["config.json"]["key"])

        slack_api_params = { 'username': preferred_name,
                             'icon_url': photo_url }

        if "link_names" not in config["config.json"] or config["config.json"]["link_names"]:
            slack_api_params["link_names"] = 1

        for relay_channel in relay_channels:
            client.chat_post_message(relay_channel,  message, **slack_api_params)


def _initialise(bot):
    _externals['BridgeInstance'] = BridgeInstance(bot, "slack", SlackAsyncListener)
