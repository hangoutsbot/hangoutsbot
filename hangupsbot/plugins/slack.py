from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from threading import Thread
from hangups.ui.utils import get_conv_name
from pyslack import SlackClient
try:
    import emoji
except ImportError:
    print("Error: You need to install the python emoji library!")

import ssl
import asyncio
import logging
import hangups

import re
from urllib.request import urlopen
import json

""" Slack plugin for listening to hangouts and slack and syncing messages between the two.
config.json will have to be configured as follows:
"slack": [{
  "certfile": null,
  "name": SERVER_NAME,
  "port": LISTENING_PORT,
  "key": SLACK_API_KEY,
  "channel": #SLACK_CHANNEL_NAME,
  "synced_conversations": ["CONV_ID1", "CONV_ID2"]
}]

You can (theoretically) set up as many slack sinks per bot as you like, by extending the list"""

def _initialise(Handlers, bot=None):
    if bot:
        _start_slack_sinks(bot)
    else:
        print("Slack sinks could not be initialized.")
    Handlers.register_handler(_handle_slackout)
    return []

def _start_slack_sinks(bot):
    # Start and asyncio event loop
    loop = asyncio.get_event_loop()

    slack_sink = bot.get_config_option('slack')
    itemNo = -1
    threads = []

    if isinstance(slack_sink, list):
        for sinkConfig in slack_sink:
            itemNo += 1

            try:
                certfile = sinkConfig["certfile"]
                if not certfile:
                    print(_("config.slack[{}].certfile must be configured").format(itemNo))
                    continue
                name = sinkConfig["name"]
                port = sinkConfig["port"]
            except KeyError as e:
                print(_("config.slack[{}] missing keyword").format(itemNo), e)
                continue

            # start up slack listener in a separate thread
            print("_start_slack_sinks()")
            t = Thread(target=start_listening, args=(
              bot,
              loop,
              name,
              port,
              certfile))

            t.daemon = True
            t.start()

            threads.append(t)

    message = _("_start_slack_sinks(): {} sink thread(s) started").format(len(threads))
    logging.info(message)

def start_listening(bot=None, loop=None, name="", port=8014, certfile=None):
    webhook = webhookReceiver

    if loop:
        asyncio.set_event_loop(loop)

    if bot:
        webhook._bot = bot

    try:
        httpd = HTTPServer((name, port), webhook)

        httpd.socket = ssl.wrap_socket(
          httpd.socket,
          certfile=certfile,
          server_side=True)

        sa = httpd.socket.getsockname()

        message = "slack: {}:{} : starting...".format(name, port)
        print(message)

        httpd.serve_forever()

    except OSError as e:
        message = "SLACK: {}:{} : {}".format(name, port, e)
        print(message)
        logging.error(message)
        logging.exception(e)

        try:
            httpd.socket.close()
        except Exception as e:
            pass

    except KeyboardInterrupt:
        httpd.socket.close()

def _slack_repeater_cleaner(bot, event, id):
    event_tokens = event.text.split(":", maxsplit=1)
    event_text = event_tokens[1].strip()
    if event_text.lower().startswith(tuple([cmd.lower() for cmd in bot._handlers.bot_command])):
        event_text = bot._handlers.bot_command[0] + " [REDACTED]"
    event.text = event_text
    event.from_bot = False
    event._slack_no_repeat = True
    event._external_source = event_tokens[0].strip() + "@slack"


class webhookReceiver(BaseHTTPRequestHandler):
    _bot = None

    def _handle_incoming(self, path, query_string, payload):
        path = path.split("/")
        conversation_id = path[1]
        if conversation_id is None:
            print(_("conversation id must be provided as part of path"))
            return

        if "text" in payload:
            try:
                text = emoji.emojize(str(payload["text"][0]), use_aliases=True)
            except NameError: # emoji library likely missing
                text = str(payload["text"][0])
                
            if "user_name" in payload:
                if "slackbot" not in str(payload["user_name"][0]):
                    text = self._remap_internal_slack_ids(text)
                    response = "<b>" + str(payload["user_name"][0]) + ":</b> " + text
                    self._scripts_push(conversation_id, response)

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
            print("_slack_get_label(): from cache {} = {}".format(id, label))
        else:
            try:
                response = urlopen(url)
                json_string = str(response.read().decode('utf-8'))
                data = json.loads(json_string)
                if type_str in data:
                    label = data[type_str]["name"]
                    self._slack_cache[type_str][id] = label
                    print("_slack_get_label(): from API {} = {}".format(id, label))
            except Exception as e:
                print("EXCEPTION in _slack_get_label(): {}".format(e))

        return prefix + label

    def _scripts_push(self, conversation_id, message):
        webhookReceiver._bot.send_html_to_conversation(
            conversation_id, 
            message + self._bot.call_shared("reprocessor.attach_reprocessor", _slack_repeater_cleaner), 
            context = {'base': {'tags': ['slack', 'relay'], 'source': 'slack', 'importance': 50}})

    def do_POST(self):
        """
           receives post, handles it
       """
        print(_('receiving POST...'))
        data_string = self.rfile.read(int(self.headers['Content-Length'])).decode('UTF-8')
        self.send_response(200)
        message = bytes('OK', 'UTF-8')
        self.send_header("Content-type", "text")
        self.send_header("Content-length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)
        print(_('connection closed'))

        # parse requested path + query string
        _parsed = urlparse(self.path)
        path = _parsed.path
        query_string = parse_qs(_parsed.query)

        print(_("incoming path: {}").format(path))

        # parse incoming data
        payload = parse_qs(data_string)

        print(_("payload {}").format(payload))

        self._handle_incoming(path, query_string, payload)


@asyncio.coroutine
def _handle_slackout(bot, event, command):
    if "_slack_no_repeat" in dir(event) and event._slack_no_repeat:
        return

    """forward messages to slack over webhook"""

    slack_sink = bot.get_config_option('slack')

    if isinstance(slack_sink, list):
        for sinkConfig in slack_sink:

            try:
                slackkey = sinkConfig["key"]
                channel = sinkConfig["channel"]
                convlist = sinkConfig["synced_conversations"]

                if event.conv_id in convlist:
                    fullname = event.user.full_name
                    response = yield from bot._client.getentitybyid([event.user_id.chat_id])
                    try:
                       photo_url = "http:" + response.entities[0].properties.photo_url
                    except Exception as e:
                        print("Slack: Could not pull avatar for {}".format(fullname))

                    client = SlackClient(slackkey)
                    client.chat_post_message(channel, event.text, username=fullname, icon_url=photo_url)
            except Exception as e:
                print("Could not handle slackout with key {} between {} and {}. is config.json properly configured?".format(slackkey,channel,convlist))
