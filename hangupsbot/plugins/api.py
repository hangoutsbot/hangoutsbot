from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from threading import Thread
from hangups.ui.utils import get_conv_name
from commands import command
from random import randrange

import json
import ssl
import asyncio
import logging
import hangups
import datetime
import plugins

def _initialise(Handlers, bot):
    if bot:
        _start_api(bot)
    else:
        print("API could not be initialized.")
    plugins.register_handler(_handle_incoming_message, type="allmessages")
    return []

""" API plugin for listening for server commands and treating them as ConversationEvents
config.json will have to be configured as follows:

"api_key": "API_KEY",
"api": [{
  "certfile": null,
  "name": SERVER_NAME,
  "port": LISTENING_PORT,
}]

"""

def _handle_incoming_message(bot, event, command):
    if event.user.is_self:
        yield from bot._handlers.handle_command(event)

def _start_api(bot):
    # Start and asyncio event loop
    loop = asyncio.get_event_loop()

    api = bot.get_config_option('api')
    itemNo = -1
    threads = []

    if isinstance(api, list):
        for sinkConfig in api:
            itemNo += 1

            try:
                certfile = sinkConfig["certfile"]
                if not certfile:
                    print(_("config.api[{}].certfile must be configured").format(itemNo))
                    continue
                name = sinkConfig["name"]
                port = sinkConfig["port"]
            except KeyError as e:
                print(_("config.api[{}] missing keyword").format(itemNo), e)
                continue

            # start up api listener in a separate thread
            print("Starting API on https://{}:{}/".format(name, port))
            t = Thread(target=start_listening, args=(
              bot,
              loop,
              name,
              port,
              certfile))

            t.daemon = True
            t.start()

            threads.append(t)

    message = _("_start_api(): {} api started").format(len(threads))
    logging.info(message)

def start_listening(bot, loop=None, name="", port=8007, certfile=None):
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
        print(_("listener: api on {}, port {}...").format(sa[0], sa[1]))

        httpd.serve_forever()
    except IOError:
        # do not run sink without https!
        print(_("listener: api : pem file possibly missing or broken (== '{}')").format(certfile))
        httpd.socket.close()
    except OSError as e:
        # Could not connect to HTTPServer!
        print(_("listener: api : requested access could not be assigned. Is something else using that port? (== '{}:{}')").format(name, port))
    except KeyboardInterrupt:
        httpd.socket.close()

class webhookReceiver(BaseHTTPRequestHandler):
    _bot = None

    def _handle_incoming(self, path, query_string, payload):

        path = path.split("/")
        if path[1] is not webhookReceiver._bot.get_config_option('api_key'):
            print(_("API Key not provided. {} doesn't match {}".format(path[1], webhookReceiver._bot.get_config_option('api_key'))))
            return

        if "content" in payload and "sendto" in payload:
            self._scripts_command(payload["sendto"], payload["content"])

        else:
            print("Invalid payload: {}".format(payload))

        print(_("handler finished"))

    def _scripts_command(self, conv_or_user_id, content):
        try:
            if not webhookReceiver._bot.send_html_to_user(conv_or_user_id, content): # Not a user id
                webhookReceiver._bot.send_html_to_conversation(conv_or_user_id, content)
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
        payload = json.loads(data_string)

        print(_("payload {}").format(payload))

        self._handle_incoming(path, query_string, payload)
