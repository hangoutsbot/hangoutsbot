import asyncio, logging

import plugins
import threadmanager

from sinks import aiohttp_start
from sinks.base_bot_request_handler import AsyncRequestHandler as IncomingRequestHandler


logger = logging.getLogger(__name__)


class WebFramework:
    def __init__(self, bot, configkey, RequestHandler=IncomingRequestHandler):
        self._bot = bot

        self.configkey = configkey
        self.configuration = bot.get_config_option(self.configkey)
        self.RequestHandler = RequestHandler

        if not self.configuration:
            logger.info("no configuration for {}, not running".format(self.configkey))
            return

        self._start_sinks(bot)

        plugins.register_handler(self._handle_websync)


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

        logger.info("webbridge.sinks: {} thread(s) started for {}".format(itemNo, self.configkey))


    def _handle_websync(self, bot, event, command):
        """Handle hangouts messages, preparing them to be sent to the
        external service
        """

        if isinstance(self.configuration, list):
            for config in self.configuration:
                try:
                    convlist = config["synced_conversations"]
                    if event.conv_id in convlist:
                        self._send_to_external_chat(bot, event, config)
                except Exception as e:
                    logger.exception("EXCEPTION in _handle_websync")

    def _send_to_external_chat(self, bot, event, config):
        logger.info("webbridge._send_to_external_chat(): {} {}".format(self.configkey, config))

