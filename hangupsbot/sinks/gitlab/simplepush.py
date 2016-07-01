"""
GitLab webhook receiver - see http://doc.gitlab.com/ee/web_hooks/web_hooks.html
"""

import asyncio
import json
import logging

from sinks.base_bot_request_handler import AsyncRequestHandler

logger = logging.getLogger(__name__)

try:
    import dateutil.parser
except ImportError:
    logger.error("missing module python_dateutil: pip3 install python_dateutil")
    raise

class webhookReceiver(AsyncRequestHandler):
    """Receive REST API posts from GitLab"""
    _bot = None

    @asyncio.coroutine
    def process_request(self, path, dummy_query_string, content):
        """Process a received POST to a given converstation"""
        path = path.split("/")
        conv_or_user_id = path[1]
        if conv_or_user_id is None:
            logger.error("conversation or user id must be provided as part of path")
            return

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as err:
            logger.exception("invalid payload @%d:%d: %s", err.lineno, err.colno, err)

        logger.error("GitLab message: %s", json.dumps(payload))

        refs = payload.get("ref", '').split("/")

        user = payload.get("user_name")
        if not user:
            user = payload["user"]["name"]

        message = ["GitLab update for [{}]({}) by __{}__".format(
            payload["project"]["name"], payload["project"]["web_url"], user)]


        if payload["object_kind"] == "push":
            message.append("Pushed {} commit(s) on {} branch:".format(
                payload["total_commits_count"], "/".join(refs[2:])))

            for commit in payload["commits"]:
                message.append("{} -- {} at [{:%c}]({})".format(
                    commit["message"], commit["author"]["name"],
                    dateutil.parser.parse(commit["timestamp"]), commit["url"]))

        elif payload["object_kind"] == "tag_push":
            message.append("Pushed tag {}]".format("/".join(refs[2:])))

        elif payload["object_kind"] == "issue":
            issue = payload["object_attributes"]
            message.append("Update {} issue {} at {:%c}\n[{}]({})".format(
                issue["state"], issue["id"],
                dateutil.parser.parse(issue["updated_at"]),
                issue["title"], issue["url"]))

        elif payload["object_kind"] == "note":
            note = payload["object_attributes"]
            message.append("{} note on {}: [{}]({})".format(
                note["notable_type"], note["id"], note["note"], note["url"]))

        elif payload["object_kind"] == "merge_request":
            request = payload["object_attributes"]
            message.append("Merge request {}: from [{}:{}]({}) to [{}:{}]({})".format(
                request["id"],
                request["source"]["name"], request["source_branch"], request["source"]["web_url"],
                request["target"]["name"], request["target_branch"], request["target"]["web_url"]))

        else:
            message.append("{}: unknown gitlab webhook object kind".format(payload["object_kind"]))
            logger.warning("%s: unknown gitlab webhook object kind", payload["object_kind"])

        if message:
            yield from self.send_data(conv_or_user_id, "\n".join(message))
