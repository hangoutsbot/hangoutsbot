import asyncio
import logging

from collections import namedtuple

import plugins
import threadmanager

from sinks import aiohttp_start
from sinks.base_bot_request_handler import AsyncRequestHandler as IncomingRequestHandler


logger = logging.getLogger(__name__)

FakeEvent = namedtuple( 'event', [ 'text',
                                   'user',
                                   'passthru' ])

FakeUser = namedtuple( 'user', [ 'full_name',
                                 'id_' ])

FakeUserID = namedtuple( 'userID', [ 'chat_id',
                                     'gaia_id' ])

class WebFramework:
    def __init__(self, bot, configkey, RequestHandler=IncomingRequestHandler):
        self.plugin_name = False
        self.bot = self._bot = bot
        self.configkey = configkey
        self.RequestHandler = RequestHandler

        if not self.load_configuration(configkey):
            logger.info("no configuration for {}, not running".format(self.configkey))
            return

        self.setup_plugin()

        if not self.plugin_name:
            logger.warning("plugin_name not defined in code, not running")
            return

        plugins.register_handler(self._broadcast, type="sending")
        plugins.register_handler(self._repeat, type="allmessages")

        self.start_listening(bot)

    def load_configuration(self, configkey):
        self.configuration = self.bot.get_config_option(self.configkey)
        return self.configuration

    def setup_plugin(self):
        logger.warning("setup_plugin should be overridden by derived class")

    def applicable_configuration(self, conv_id):
        """standardised configuration structure:

            "<EXTERNAL_CHAT_NAME>": [
                {
                    "bot_api_key": <api key(s) for bot>,
                    "hangouts": [
                        "<at least 1 internal chat/group/team id>"
                    ],
                    "<EXTERNAL_CHAT_NAME>": [
                        "<at least 1 external chat/group/team id>"
                    ]
                }
            ]

        """

        applicable_configurations = []
        for configuration in self.configuration:
            if conv_id in configuration["hangouts"]:
                applicable_configurations.append({ "trigger": conv_id,
                                                   "config.json": configuration })

        return applicable_configurations

    @asyncio.coroutine
    def _broadcast(self, bot, broadcast_list, context):
        conv_id = broadcast_list[0][0]
        message = broadcast_list[0][1]
        image_id = broadcast_list[0][2]

        applicable_configurations = self.applicable_configuration(conv_id)
        if not applicable_configurations:
            return

        passthru = context["passthru"]

        if "norelay" not in passthru:
            passthru["norelay"] = []
        if self.plugin_name in passthru["norelay"]:
            # prevent message broadcast duplication
            logger.info("NORELAY:_broadcast {}".format(passthru["norelay"]))
            return
        else:
            # halt messaging handler from re-relaying
            passthru["norelay"].append(self.plugin_name)

        myself = bot.user_self()
        chat_id = myself['chat_id']
        fullname = myself['full_name']

        # context preserves as much of the original request as possible
        if "original_request" in passthru:
            message = passthru["original_request"]["message"]
            image_id = passthru["original_request"]["image_id"]
            segments = passthru["original_request"]["segments"]
            if "user" in passthru["original_request"]:
                if(isinstance(passthru["original_request"]["user"], str)):
                    user = FakeUser( full_name = str,
                                     id_ = FakeUserID( chat_id = chat_id,
                                                       gaia_id = chat_id ))
                    pass
                else:
                    user = passthru["original_request"]["user"]

        # for messages from other plugins, relay them
        for config in applicable_configurations:
            yield from self._send_to_external_chat( config,
                                                    FakeEvent( text = message,
                                                               user = user,
                                                               passthru = passthru ))

    @asyncio.coroutine
    def _repeat(self, bot, event, command):
        conv_id = event.conv_id

        applicable_configurations = self.applicable_configuration(conv_id)
        if not applicable_configurations:
            return

        passthru = event.passthru

        if "norelay" not in passthru:
            passthru["norelay"] = []
        if self.plugin_name in passthru["norelay"]:
            # prevent message relay duplication
            logger.info("NORELAY:_repeat {}".format(passthru["norelay"]))
            return
        else:
            # halt sending handler from re-relaying
            passthru["norelay"].append(self.plugin_name)

        user = event.user
        message = event.text
        image_id = None

        if "original_request" in passthru:
            message = passthru["original_request"]["message"]
            image_id = passthru["original_request"]["image_id"]
            segments = passthru["original_request"]["segments"]
            # user is only assigned once, upon the initial event
            if "user" in passthru["original_request"]:
                user = passthru["original_request"]["user"]
            else:
                passthru["original_request"]["user"] = user
        else:
            # user raised an event
            passthru["original_request"] = { "message": event.text,
                                             "image_id": None, # XXX: should be attachments
                                             "segments": event.conv_event.segments,
                                             "user": event.user }

        for config in applicable_configurations:
            yield from self._send_to_external_chat(config, event)

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        pass

    @asyncio.coroutine
    def _send_to_internal_chat(self, conv_id, event):
        ### XXX: temp
        if isinstance(event.passthru["original_request"]["user"], str):
            full_name = event.passthru["original_request"]["user"]
        else:
            full_name = event.passthru["original_request"]["user"].full_name

        yield from self.bot.coro_send_message(
            conv_id,
            "{}: {}".format( full_name,
                             event.passthru["original_request"]["message"] ),
            image_id = event.passthru["original_request"]["image_id"],
            context = { "passthru": event.passthru })

    def _format_message(self, message, asUser):
        if isinstance(asUser, str):
            formatted_message = "{}: {}".format(asUser, message)
        else:
            print("{} {}".format(type(asUser), asUser))
            formatted_message = "{}: {}".format(asUser.full_name, message)

        return formatted_message

    def start_listening(self, bot):
        loop = asyncio.get_event_loop()

        itemNo = -1
        threads = []

        if isinstance(self.configuration, list):
            for listener in self.configuration:
                itemNo += 1

                try:
                    certfile = listener["certfile"]
                    if not certfile:
                        logger.warning("config.{}[{}].certfile must be configured".format(self.configkey, itemNo))
                        continue
                    name = listener["name"]
                    port = listener["port"]
                except KeyError as e:
                    logger.warning("config.{}[{}] missing keyword".format(self.configkey, itemNo))
                    continue

                aiohttp_start(
                    bot,
                    name,
                    port,
                    certfile,
                    self.RequestHandler,
                    "webbridge." + self.configkey)

        logger.info("webbridge.sinks: {} thread(s) started for {}".format(itemNo + 1, self.configkey))
