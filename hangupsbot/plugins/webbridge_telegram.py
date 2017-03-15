import aiohttp, asyncio, json, logging, requests

import plugins

from webbridge import WebFramework, IncomingRequestHandler

logger = logging.getLogger(__name__)


class BridgeInstance(WebFramework):

    def _repeat(self, bot, event, command):
        conv_id = event.conv_id

        applicable_configurations = self.applicable_configuration(conv_id)
        if not applicable_configurations:
            return

        passthru = event.passthru

        if "norelay" not in passthru:
            passthru["norelay"] = []
        if __name__ in passthru["norelay"]:
            # prevent message relay duplication
            logger.info("NORELAY:_repeat {}".format(passthru["norelay"]))
            return
        else:
            # halt sending handler from re-relaying
            passthru["norelay"].append(__name__)

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
            self._send_to_external_chat(event, config)


    def _send_to_external_chat(self, event, config):
        conv_id = config["trigger"]
        external_ids = config["config.json"][self.configkey]

        ### XXX: still incomplete, refer to slack implementation
        message = event.passthru["original_request"]["message"]
        if isinstance(event.passthru["original_request"]["user"], str):
            fullname = event.passthru["original_request"]["user"]
        else:
            fullname = event.passthru["original_request"]["user"].full_name

        for eid in external_ids:
            asyncio.async(
                self.telegram_api_request("sendMessage", {
                    "chat_id" : eid, 
                    "text" : fullname + " : " + message })
            ).add_done_callback(lambda future: future.result())


    @asyncio.coroutine
    def _send_to_internal_chat(self, messagedata, conv_id):
        message = messagedata["message"]

        user = message["from"]["username"] + "@tg"
        if "text" in message:
            original_message = message["text"]
            message = "{}: {}".format(user, message["text"])
        elif "photo" in message:
            original_message = "(photo)"
            message = "{} send a photo".format(user)
        else:
            message = original_message = "unrecognised telegram update: {}".format(message)

        passthru = {
            "original_request": {
                "message": original_message,
                "image_id": None,
                "segments": None,
                "user": user },
            "norelay": [ __name__ ]}

        yield from self.bot.coro_send_message(
            conv_id,
            message,
            context = {
                "base": {
                    'tags': ['telegram', 'relay'], 
                    'source': 'slack', 
                    'importance': 50 },
                "passthru": passthru })


    def _start_sinks(self, bot):
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
                        message = Update["message"]
                        if str(message["chat"]["id"]) in configuration[self.configkey]:
                            for conv_id in configuration["hangouts"]:
                                yield from self._send_to_internal_chat(Update, conv_id)

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
