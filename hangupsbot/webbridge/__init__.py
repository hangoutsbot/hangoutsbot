import asyncio, logging

import plugins
import threadmanager

from sinks import aiohttp_start
from sinks.base_bot_request_handler import AsyncRequestHandler as IncomingRequestHandler


logger = logging.getLogger(__name__)


class WebFramework:
    def __init__(self, bot, configkey, RequestHandler=IncomingRequestHandler):
        self._bot = bot

        self.bot = bot
        self.configkey = configkey
        self.RequestHandler = RequestHandler

        if not self.load_configuration(bot, configkey):
            logger.info("no configuration for {}, not running".format(self.configkey))
            return

        self._start_sinks(bot)

        plugins.register_handler(self._broadcast, type="sending")
        plugins.register_handler(self._repeat, type="allmessages")


    def load_configuration(self, bot, configkey):
        self.configuration = bot.get_config_option(self.configkey)
        return self.configuration

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

    def _broadcast(self, bot, broadcast_list, context):
        conv_id = broadcast_list[0][0]
        message = broadcast_list[0][1]
        image_id = broadcast_list[0][2]

        applicable_configurations = self.applicable_configuration(conv_id)
        if not applicable_configurations:
            return

        ### XXX: RELAY STUFF


    def _repeat(self, bot, event, command):
        if isinstance(self.configuration, list):
            for config in self.configuration:
                try:
                    convlist = config["synced_conversations"]
                    if event.conv_id in convlist:
                        self._send_to_external_chat(bot, event, config)
                except Exception as e:
                    logger.exception("EXCEPTION in _handle_websync")


    def _send_to_external_chat(self, event, config):
        logger.info("webbridge._send_to_external_chat(): {} {}".format(self.configkey, config))


    def _start_sinks(self, bot):
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
