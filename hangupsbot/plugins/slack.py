""" Slack plugin for listening to hangouts and slack and syncing messages between the two.
config.json will have to be configured as follows:
"slack": [{
  "certfile": null,
  "name": SERVER_NAME,
  "port": LISTENING_PORT,
  "key": SLACK_API_KEY,
  "channel": #SLACK_CHANNEL_NAME,
  "synced_conversations": ["CONV_ID1", "CONV_ID2"],
  "otr_privacy" : true/false
}]

You can (theoretically) set up as many slack sinks per bot as you like, by extending the list"""
import asyncio, logging, json, re

from html import unescape
from urllib.parse import parse_qs
from urllib.request import urlopen

from aiohttp import web

import emoji

from pyslack import SlackClient

import plugins

from sinks import aiohttp_start
from sinks.base_bot_request_handler import AsyncRequestHandler

import hangups


logger = logging.getLogger(__name__)


def _initialise(bot):
    _start_slack_sinks(bot)

    plugins.register_handler(_broadcast, type="sending")
    plugins.register_handler(_repeat, type="allmessages")

    return []

    plugins.register_user_command(["slackusers"])


def _start_slack_sinks(bot):
    # Start and asyncio event loop
    loop = asyncio.get_event_loop()

    slack_sink = bot.get_config_option('slack')
    itemNo = -1

    if isinstance(slack_sink, list):
        for sinkConfig in slack_sink:
            itemNo += 1

            try:
                certfile = sinkConfig["certfile"]
                if not certfile:
                    logger.error("config.slack[{}].certfile must be configured".format(itemNo))
                    continue
                name = sinkConfig["name"]
                port = sinkConfig["port"]
            except KeyError as e:
                logger.error("config.slack[{}] missing keyword".format(itemNo), e)
                continue

            aiohttp_start(bot, name, port, certfile, SlackAsyncListener, group=__name__)

    logger.info("{} slack listeners started".format(itemNo + 1))


class SlackAsyncListener(AsyncRequestHandler):
    def process_request(self, path, query_string, content):
        payload  = parse_qs(content)

        path = path.split("/")
        conversation_id = path[1]
        if not conversation_id:
            raise ValueError("conversation id must be provided in path")

        if "text" in payload:
            try:
                text = emoji.emojize(str(payload["text"][0]), use_aliases=True)
            except NameError: # emoji library likely missing
                text = str(payload["text"][0])
                
            if "user_name" in payload:
                if "slackbot" not in str(payload["user_name"][0]):
                    text = self._remap_internal_slack_ids(text)

                    user = payload["user_name"][0] + "@slack"
                    original_message = unescape(text)

                    message = "{}: {}".format(user, original_message)
                    passthru = {
                        "original_request": {
                            "message": original_message,
                            "image_id": None,
                            "segments": None,
                            "user": user },
                        "norelay": [ __name__ ]}

                    yield from self.send_data(
                        conversation_id,
                        message,
                        context = {
                            "base": {
                                'tags': ['slack', 'relay'], 
                                'source': 'slack', 
                                'importance': 50 },
                            "passthru": passthru })


    def _remap_internal_slack_ids(self, text):
        text = self._slack_label_users(text)
        text = self._slack_label_channels(text)
        return text

    def _slack_label_users(self, text):
        for fragment in re.findall("(<@([A-Z0-9]+)(\|[^>]*?)?>)", text):
            """detect and map <@Uididid> and <@Uididid|namename>"""
            full_token = fragment[0]
            id = full_token[2:-1].split("|", maxsplit=1)[0]
            username = self._slack_get_label(id, "user")
            text = text.replace(full_token, username)
        return text

    def _slack_label_channels(self, text):
        for fragment in re.findall("<#[A-Z0-9]+>", text):
            id = fragment[2:-1]
            username = self._slack_get_label(id, "channel")
            text = text.replace(fragment, username)
        return text

    _slack_cache = {"user": {}, "channel": {}}

    def _slack_get_label(self, id, type_str):
        # hacky way to get the first token:
        slack_sink_configuration = self._bot.get_config_option('slack')
        token = slack_sink_configuration[0]["key"]

        prefix = "?"
        if type_str == "user":
            url = 'https://slack.com/api/users.info?token=' + token + '&user=' + id
            prefix = "@"
        elif type_str == "channel":
            url = 'https://slack.com/api/channels.info?token=' + token + '&channel=' + id
            prefix = "#"
        else:
            raise ValueError('unknown label type_str')

        label = "UNKNOWN"
        if id in self._slack_cache[type_str]:
            label = self._slack_cache[type_str][id]
            logger.debug("slack label resolved from cache: {} = {}".format(id, label))
        else:
            try:
                response = urlopen(url)
                json_string = str(response.read().decode('utf-8'))
                data = json.loads(json_string)
                if type_str in data:
                    label = data[type_str]["name"]
                    self._slack_cache[type_str][id] = label
                    logger.debug("slack label resolved from API: {} = {}".format(id, label))

            except Exception as e:
                logger.exception("FAILED to resolve slack label for {}".format(id))

        return prefix + label


@asyncio.coroutine
def _broadcast(bot, broadcast_list, context):
    target_conv_id = broadcast_list[0][0]
    message = broadcast_list[0][1]
    image_id = broadcast_list[0][2]

    slackChannelConfigs = bot.get_config_option('slack')
    if not isinstance(slackChannelConfigs, list):
        return

    channelConfigs = []
    for channelConfig in slackChannelConfigs:
        if target_conv_id in channelConfig["synced_conversations"]:
            channelConfigs.append(channelConfig)
    if not channelConfigs:
        return

    passthru = context["passthru"]

    if "norelay" not in passthru:
        passthru["norelay"] = []
    if __name__ in passthru["norelay"]:
        # prevent message broadcast duplication
        logger.info("NORELAY:_broadcast {}".format(passthru["norelay"]))
        return
    else:
        # halt messaging handler from re-relaying
        passthru["norelay"].append(__name__)

    myself = bot.user_self()
    chat_id = myself['chat_id']
    fullname = myself['full_name']

    # context preserves as much of the original request as possible
    if "original_request" in passthru:
        message = passthru["original_request"]["message"]
        image_id = passthru["original_request"]["image_id"]
        segments = passthru["original_request"]["segments"]
        if "user" in passthru["original_request"]:
            if(isinstance(passthru["original_request"]["user"], str)):
                pass
            else:
                chat_id = passthru["original_request"]["user"].id_.chat_id
                # message line formatting: leave it to slack

    # for messages from other plugins, relay them
    for config in channelConfigs:
        logger.info("BROADCASTING: {} - {}".format(message, passthru))
        yield from _slack_send(bot, config, message, chat_id, passthru)


@asyncio.coroutine
def _repeat(bot, event, command):
    """formerly _handle_slackout
    forward messages to slack over webhook"""

    slackChannelConfigs = bot.get_config_option('slack')
    if not isinstance(slackChannelConfigs, list):
        return

    channelConfigs = []
    for channelConfig in slackChannelConfigs:
        if event.conv_id in channelConfig["synced_conversations"]:
            channelConfigs.append(channelConfig)
    if not channelConfigs:
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

    for config in channelConfigs:
        logger.info("REPEATING: {} - {}".format(message, passthru))
        yield from _slack_send(bot, config, message, user.id_.chat_id, passthru)


@asyncio.coroutine
def _slack_send(bot, sinkConfig, message, chat_id, passthru):

    _response = yield from bot._client.get_entity_by_id(
        hangups.hangouts_pb2.GetEntityByIdRequest(
            request_header = bot._client.get_request_header(),
            batch_lookup_spec = [
                hangups.hangouts_pb2.EntityLookupSpec(
                    gaia_id = chat_id )]))

    try:
        photo_url = "http:" + _response.entity[0].properties.photo_url
    except Exception as e:
        logger.exception("FAILED to acquire photo_url for {}".format(fullname))
        photo_url = None

    if "original_request" in passthru:
        message = passthru["original_request"]["message"]
        if isinstance(passthru["original_request"]["user"], str):
            fullname = passthru["original_request"]["user"]
        else:
            fullname = _response.entity[0].properties.display_name;

    try:
        try:
            client = SlackClient(sinkConfig["key"], verify=True)
        except TypeError:
            client = SlackClient(sinkConfig["key"])

        slack_api_params = { 'username': fullname,
                             'icon_url': photo_url }

        if "link_names" not in sinkConfig or sinkConfig["link_names"]:
            logger.debug("slack api link_names is active")
            slack_api_params["link_names"] = 1

        client.chat_post_message(sinkConfig["channel"],  message, **slack_api_params)
    except Exception as e:
        logger.exception( "Could not handle slackout with key {} between {} and {}. "
                          "Is config.json properly configured?".format( slackkey,
                                                                        channel ))


def slackusers(bot, event, *args):
    slack_sink = bot.get_config_option('slack')
    if isinstance(slack_sink, list):
        for sinkConfig in slack_sink:
            slackkey = sinkConfig["key"]
            channel = sinkConfig["channel"]
            convlist = sinkConfig["synced_conversations"]

            if event.conv_id in convlist:
                try:
                    client = SlackClient(slackkey, verify=True)
                except TypeError:
                    client = SlackClient(slackkey)

                chan_id = client.channel_name_to_id(channel)
                slack_api_params = {'channel': chan_id}
                info = client._make_request('channels.info', slack_api_params)
                msg =  "Slack channel {}: {}".format(info['channel']['name'],
                                                       info['channel']['topic']['value'])
                users = {}
                for uid in info['channel']['members']:
                    slack_api_params = {'user': uid}
                    user = client._make_request('users.info', slack_api_params)
                    if user["ok"] and user['user']:
                        username = user['user']['name']
                        realname = user['user'].get('real_name', "No real name")
                        users[username] = realname

                msg += "\n{} members:".format(len(users))

                for username, realname in sorted(users.items()):
                    msg += "\n  {}: {}".format(username, realname)

                yield from bot.coro_send_message(event.conv, msg)
