import aiohttp, asyncio, json, logging, requests

import plugins

from webbridge import WebFramework, IncomingRequestHandler

logger = logging.getLogger(__name__)


class BridgeInstance(WebFramework):

    def _handle_websync(self, bot, event, command):
        for mapped in self.configuration[0]["conversation_map"]:
            if event.conv_id in mapped["hangouts"]:
                if event.from_bot:
                    # don't send my own messages
                    continue

                event_timestamp = event.timestamp

                conversation_id = event.conv_id
                conversation_text = event.text

                user_full_name = event.user.full_name
                user_id = event.user_id

                for telegram_id in mapped["telegram"]:
                    asyncio.async(
                        self.telegram_api_request("sendMessage", { "chat_id" : telegram_id, 
                                                                   "text" : user_full_name + " : " + conversation_text })
                    ).add_done_callback(lambda future: future.result())


    def _start_sinks(self, bot):
        plugins.start_asyncio_task(self.telegram_longpoll)


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


    @asyncio.coroutine
    def telegram_longpoll(self, bot):
        connector = aiohttp.TCPConnector(verify_ssl=True)
        headers = {'content-type': 'application/x-www-form-urlencoded'}

        BOT_API_KEY = self.configuration[0]["bot_api_key"]

        CONNECT_TIMEOUT = 90
        url = "https://api.telegram.org/bot{}/getUpdates".format(BOT_API_KEY)

        logger.info('Opening new long-polling request')

        max_offset = -1

        while True:
            try:
                data = { "timeout": 60 }
                if max_offset:
                    data["offset"] = int(max_offset) + 1
                res = yield from asyncio.wait_for(aiohttp.request('post', url, data=data, headers=headers, connector=connector), CONNECT_TIMEOUT)
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
                    for Update in response["result"]:
                        max_offset = Update["update_id"]
                        message = Update["message"]

                        if "text" in message:
                            text_message = message["from"]["username"] + " : " + message["text"]
                        elif "photo" in message:
                            text_message = message["from"]["username"] + " sent a photo on telegram"
                        else:
                            text_message = "unrecognised telegram update: {}".format(message)

                        for mapped in self.configuration[0]["conversation_map"]:
                            telegram = mapped["telegram"]
                            if str(message["chat"]["id"]) in telegram:
                                for conv_id in mapped["hangouts"]:
                                    yield from bot.coro_send_message( conv_id, 
                                                                      text_message )

                    logger.debug(response)
            else:
                # Close the response to allow the connection to be reused for
                # the next request.
                res.close()
                break

        logger.critical("long-polling terminated")


def _initialise(bot):
    BridgeInstance(bot, "telegram")
