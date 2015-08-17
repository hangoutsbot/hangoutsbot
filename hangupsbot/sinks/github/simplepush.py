import asyncio, json, logging

from sinks.base_bot_request_handler import AsyncRequestHandler


logger = logging.getLogger(__name__)


class webhookReceiver(AsyncRequestHandler):
    _bot = None

    @asyncio.coroutine
    def process_request(self, path, query_string, content):
        path = path.split("/")
        conv_or_user_id = path[1]
        if conv_or_user_id is None:
            logger.error("conversation or user id must be provided as part of path")
            return

        try:
            payload = json.loads(content)
        except Exception as e:
            logger.exception("invalid payload")

        if "repository" in payload and "commits" in payload and "pusher" in payload:
            html = '<b>{0}</b> has <a href="{2}">pushed</a> {1} commit(s)<br />'.format( payload["pusher"]["name"],
                                                                                         len(payload["commits"]),
                                                                                         payload["repository"]["url"] )

            for commit in payload["commits"]:
                html += '* <i>{0}</i> <a href="{2}">link</a><br />'.format( commit["message"],
                                                                            commit["author"]["name"],
                                                                            commit["url"],
                                                                            commit["timestamp"],
                                                                            commit["id"] )

            yield from self.send_data(conv_or_user_id, html)

        elif "zen" in payload:
            logger.info("github zen received: {}".format(payload["zen"]))

        else:
            logger.error("unrecognised payload: {}".format(payload))
