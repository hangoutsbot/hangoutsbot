from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import json

class webhookReceiver(BaseHTTPRequestHandler):
    _bot = None

    def _handle_incoming(self, path, query_string, payload):
        path = path.split("/")
        conv_or_user_id = path[1]
        if conv_or_user_id is None:
            print(_("conversation or user id must be provided as part of path"))
            return

        if "message" in payload:
            self._scripts_push(conv_or_user_id, payload["message"])
        else:
            print(payload)

        print(_("handler finished"))

    def _scripts_push(self, conv_or_user_id, message):
        try:
            if not webhookReceiver._bot.send_html_to_user(conv_or_user_id, message): # Not a user id
                webhookReceiver._bot.send_html_to_conversation(conv_or_user_id, message)
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
