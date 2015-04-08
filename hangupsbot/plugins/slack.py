from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from threading import Thread
from hangups.ui.utils import get_conv_name
from pyslack import SlackClient

import ssl
import asyncio
import logging
import hangups

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
        print(_("listener: slack sink on {}, port {}...").format(sa[0], sa[1]))

        httpd.serve_forever()
    except IOError:
        # do not run sink without https!
        print(_("listener: slack : pem file possibly missing or broken (== '{}')").format(certfile))
        httpd.socket.close()
    except OSError as e:
        # Could not connect to HTTPServer!
        print(_("listener: slack : requested access could not be assigned. Is something else using that port? (== '{}:{}')").format(name, port))
    except KeyboardInterrupt:
        httpd.socket.close()

class webhookReceiver(BaseHTTPRequestHandler):
    _bot = None

    def _handle_incoming(self, path, query_string, payload):
        path = path.split("/")
        conversation_id = path[1]
        if conversation_id is None:
            print(_("conversation id must be provided as part of path"))
            return

        if "text" in payload and "user_name" in payload:
            if "slackbot" not in str(payload["user_name"][0]):
                response = "<b>" + str(payload["user_name"][0]) + ":</b> " + str(payload["text"][0])
                self._scripts_push(conversation_id, response)
        else:
            print(payload)

        print(_("handler finished"))

    def _scripts_push(self, conversation_id, message):
        try:
            if not webhookReceiver._bot.send_html_to_user(conversation_id, message):
                webhookReceiver._bot.send_html_to_conversation(conversation_id, message)
        except Exception as e:
            print(e)

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
                        photo_url = "http:" + response['entity'][0]['properties']['photo_url']
                    except Exception as e:
                        print("Slack: Could not pull avatar for {}".format(fullname))

                    client = SlackClient(slackkey)
                    client.chat_post_message(channel, event.text, username=fullname, icon_url=photo_url)
            except Exception as e:
                print("Could not handle slackout, is config.json properly configured?")
