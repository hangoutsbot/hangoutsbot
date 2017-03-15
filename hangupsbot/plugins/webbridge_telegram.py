import aiohttp
import asyncio
import json
import logging
import requests

import plugins

from webbridge import ( WebFramework,
                        IncomingRequestHandler,
                        FakeEvent )

logger = logging.getLogger(__name__)


class BridgeInstance(WebFramework):
    def setup_plugin(self):
        self.plugin_name = "telegramBasic"

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        conv_id = config["trigger"]
        external_ids = config["config.json"][self.configkey]

        user = event.passthru["original_request"]["user"]
        message = event.passthru["original_request"]["message"]

        for eid in external_ids:
            yield from self.telegram_api_request("sendMessage", {
                "chat_id" : eid, 
                "text" : self._format_message(message, user) })

    def start_listening(self, bot):
        for configuration in self.configuration:
            plugins.start_asyncio_task(self.telegram_longpoll, configuration)

    @asyncio.coroutine
    def telegram_longpoll(self, bot, configuration, CONNECT_TIMEOUT=90):
        BOT_API_KEY = configuration["bot_api_key"]

        connector = aiohttp.TCPConnector(verify_ssl=True)
        headers = {'content-type': 'application/x-www-form-urlencoded'}

        url = "https://api.telegram.org/bot{}/getUpdates".format(BOT_API_KEY)

        logger.info('Opening new long-polling request')

        max_offset = -1

        while True:
            try:
                data = { "timeout": 60 }
                if max_offset:
                    data["offset"] = int(max_offset) + 1
                res = yield from asyncio.wait_for(
                    aiohttp.request( 'post',
                                     url,
                                     data=data,
                                     headers=headers,
                                     connector=connector ), CONNECT_TIMEOUT)
                chunk = yield from res.content.read(1024*1024)
            except asyncio.TimeoutError:
                raise
            except asyncio.CancelledError:
                # Prevent ResourceWarning when channel is disconnected.
                res.close()
                raise

            if chunk:
                response = json.loads(chunk.decode("utf-8"))
                if len(response["result"]) > 0:
                    # results is a list of external chat events
                    for Update in response["result"]:
                        max_offset = Update["update_id"]
                        raw_message = Update["message"]

                        if str(raw_message["chat"]["id"]) in configuration[self.configkey]:
                            for conv_id in configuration["hangouts"]:
                                user = raw_message["from"]["username"] + "@tg"

                                if "text" in raw_message:
                                    message = raw_message["text"]
                                elif "photo" in message:
                                    message = "(photo)"
                                else:
                                    message = "unrecognised telegram update: {}".format(raw_message)

                                yield from self._send_to_internal_chat(
                                    conv_id,
                                    FakeEvent(
                                        text = message,
                                        user = user,
                                        passthru = {
                                            "original_request": {
                                                "message": message,
                                                "image_id": None,
                                                "segments": None,
                                                "user": user },
                                            "norelay": [ self.plugin_name ] }))

            else:
                # Close the response to allow the connection to be reused for
                # the next request.
                res.close()
                break

        logger.critical("long-polling terminated")

    @asyncio.coroutine
    def telegram_api_request(self, method, data):
        connector = aiohttp.TCPConnector(verify_ssl=True)
        headers = {'content-type': 'application/x-www-form-urlencoded'}

        BOT_API_KEY = self.configuration[0]["bot_api_key"]

        url = "https://api.telegram.org/bot{}/{}".format(BOT_API_KEY, method)

        logger.debug(url)
        r = yield from aiohttp.request('post', url, data=data, headers=headers, connector=connector)
        raw = yield from r.text()
        logger.debug(raw)

        return raw


def _initialise(bot):
    BridgeInstance(bot, "telegram")
