import asyncio, logging

import plugins
import thread_manager

from sinks import start_listening
from sinks.base_bot_request_handler import BaseBotRequestHandler as IncomingRequestHandler


class ChatFramework:
    def __init__(self, bot, configkey, RequestHandler=IncomingRequestHandler):
        self._bot = bot

        self.configkey = configkey
        self.configuration = bot.get_config_option(self.configkey)
        self.RequestHandler = RequestHandler

        if not self.configuration:
            print("chatbridge: no configuration for {}, aborting...".format(self.configkey))
            return

        self._start_chat_sinks(bot)

        plugins.register_handler(self._handle_chatsync)


    def _start_chat_sinks(self, bot):
        loop = asyncio.get_event_loop()

        itemNo = -1
        threads = []

        if isinstance(self.configuration, list):
            for listener in self.configuration:
                itemNo += 1

                try:
                    certfile = listener["certfile"]
                    if not certfile:
                        print(_("config.{}[{}].certfile must be configured").format(self.configkey, itemNo))
                        continue
                    name = listener["name"]
                    port = listener["port"]
                except KeyError as e:
                    print(_("config.{}[{}] missing keyword").format(self.configkey, itemNo), e)
                    continue

                thread_manager.start_thread(start_listening, args=(
                    bot,
                    loop,
                    name,
                    port,
                    certfile,
                    self.RequestHandler,
                    self.configkey))

        message = _("chatbridge.sinks: {} thread(s) started for {}").format(itemNo, self.configkey)
        logging.info(message)


    def _handle_chatsync(self, bot, event, command):
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
                    print("Could not handle external chat syncing. is config.json properly configured?", e)

    def _send_to_external_chat(self, bot, event, config):
        print("chatbridge._send_to_external_chat(): {} {}".format(self.configkey, config))

