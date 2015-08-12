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

from aiohttp import web

from sinks import aiohttp_start
from sinks.base_bot_request_handler import AsyncRequestHandler


logger = logging.getLogger(__name__)


def _initialise(bot):
    _start_api(bot)


def _reprocess_the_event(bot, event, id):
    event.from_bot = False
    event._syncroom_no_repeat = True


def _start_api(bot):
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

            aiohttp_start(bot, name, port, certfile, APIRequestHandler, group=__name__)


class APIRequestHandler(AsyncRequestHandler):
    def addroutes(self, router):
        router.add_route("POST", "/", self.adapter_do_POST)
        router.add_route('GET', '/{api_key}/{id}/{message:.*?}', self.adapter_do_GET)


    @asyncio.coroutine
    def adapter_do_GET(self, request):
        payload = { "sendto": request.match_info["id"],
                    "key": request.match_info["api_key"],
                    "content": unquote(request.match_info["message"]) }

        results = yield from self.process_request( '', # IGNORED
                                                   '', # IGNORED
                                                   payload )
        if not results:
            results = "OK"

        return web.Response(body=results.encode('utf-8'))

    @asyncio.coroutine
    def process_request(self, path, query_string, content):
        # XXX: bit hacky due to different routes...
        payload = content
        if isinstance(payload, str):
            # XXX: POST - payload in incoming request BODY (and not yet parsed, do it here)
            payload = json.loads(payload)
        # XXX: else GET - everything in query string (already parsed before it got here)

        api_key = self._bot.get_config_option("api_key")

        if payload["key"] != api_key:
            raise ValueError("API key does not match")

        results = yield from self.send_actionable_message(payload["sendto"], payload["content"])

        return results

    @asyncio.coroutine
    def send_actionable_message(self, id, content):
        """reprocessor: allow message to be intepreted as a command"""
        content = content + self._bot.call_shared("reprocessor.attach_reprocessor", _reprocess_the_event)

        if id in self._bot.conversations.catalog:
            results = yield from self._bot.coro_send_message(id, content)
        else:
            # attempt to send to a user id
            results = yield from self._bot.coro_send_to_user(id, content)

        return results
