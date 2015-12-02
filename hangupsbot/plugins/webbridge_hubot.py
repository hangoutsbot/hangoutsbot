import aiohttp, asyncio, json, logging, requests

import plugins

from webbridge import WebFramework, IncomingRequestHandler


logger = logging.getLogger(__name__)


class BridgeInstance(WebFramework):
    def _send_to_external_chat(self, bot, event, config):
        """override WebFramework._send_to_external_chat()"""
        if event.from_bot:
            # don't send my own messages
            return

        event_timestamp = event.timestamp

        conversation_id = event.conv_id
        conversation_text = event.text

        user_full_name = event.user.full_name
        user_id = event.user_id

        url = config["HUBOT_URL"] + conversation_id
        payload = {"from" : str(user_id.chat_id), "message" : conversation_text}
        headers = {'content-type': 'application/json'}

        connector = aiohttp.TCPConnector(verify_ssl=False)
        asyncio.async(
            aiohttp.request('post', url, data = json.dumps(payload), headers = headers, connector=connector)
        ).add_done_callback(lambda future: future.result())


class IncomingMessages(IncomingRequestHandler):
    @asyncio.coroutine
    def process_request(self, path, query_string, content):
        path = path.split("/")
        conversation_id = path[1]
        if conversation_id is None:
            logger.error("conversation id must be provided as part of path")
            return

        payload = json.loads(content)

        yield from self.send_data(conversation_id, payload["message"])


def _initialise(bot):
    BridgeInstance(bot, "hubot", IncomingMessages)

