"""API plugin for listening for server commands and treating them as ConversationEvents
config.json will have to be configured as follows:

"api_key": "API_KEY",
"api": [{
  "certfile": null,
  "name": "SERVER_NAME",
  "port": LISTENING_PORT
}]

Also you will need to append the bot's own user_id to the admin list if you want
to be able to run admin commands externally

More info: https://github.com/hangoutsbot/hangoutsbot/wiki/API-Plugin
"""
import asyncio, json, logging

import hangups

import threadmanager

from urllib.parse import urlparse, parse_qs, unquote

from sinks import start_listening
from sinks.base_bot_request_handler import BaseBotRequestHandler


logger = logging.getLogger(__name__)


def _initialise(bot):
    _start_api(bot)


def _reprocess_the_event(bot, event, id):
    event.from_bot = False
    event._syncroom_no_repeat = True


def _start_api(bot):
    # Start and asyncio event loop
    loop = asyncio.get_event_loop()

    api = bot.get_config_option('api')
    itemNo = -1

    if isinstance(api, list):
        for sinkConfig in api:
            itemNo += 1

            try:
                certfile = sinkConfig["certfile"]
                if not certfile:
                    print("config.api[{}].certfile must be configured".format(itemNo))
                    continue
                name = sinkConfig["name"]
                port = sinkConfig["port"]
            except KeyError as e:
                print("config.api[{}] missing keyword".format(itemNo), e)
                continue

            logger.info("started on https://{}:{}/".format(name, port))

            threadmanager.start_thread(start_listening, args=(
                bot,
                loop,
                name,
                port,
                certfile,
                APIRequestHandler,
                "plugin-api"))


class APIRequestHandler(BaseBotRequestHandler):
    _bot = None

    def do_GET(self):
        """handle incoming GET request
        everything is contained in the URL
        """
        print('{}: receiving GET...'.format(self.sinkname))

        message = bytes('OK', 'UTF-8')
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(message)
        print('{}: connection closed'.format(self.sinkname))

        _parsed = urlparse(self.path)
        path = _parsed.path
        query_string = parse_qs(_parsed.query)
        tokens = path.split("/", maxsplit=3)

        if len(tokens) != 4:
            return

        try:
            print("SECURITY WARNING: sending API commands via GET is INSECURE, please use POST")

            payload = {
                "key": str(tokens[1]), 
                "sendto": str(tokens[2]), 
                "content": unquote(str(tokens[3]))}

            # process the payload
            asyncio.async(
                self.process_request(path, query_string, payload)
            ).add_done_callback(lambda future: future.result())

        except Exception as e:
            logger.exception(e)


    @asyncio.coroutine
    def process_request(self, path, query_string, content):

        payload = content
        if isinstance(payload, str):
            payload = json.loads(payload)

        api_key = self._bot.get_config_option("api_key")

        if payload["key"] != api_key:
            raise ValueError("API key does not match")

        yield from self.send_actionable_message(payload["sendto"], payload["content"])


    @asyncio.coroutine
    def send_actionable_message(self, id, content):
        """reprocessor: allow message to be intepreted as a command"""
        content = content + self._bot.call_shared("reprocessor.attach_reprocessor", _reprocess_the_event)

        if id in self._bot.conversations.catalog:
            yield from self._bot.coro_send_message(id, content)
        else:
            # attempt to send to a user id
            yield from self._bot.coro_send_to_user(id, content)
