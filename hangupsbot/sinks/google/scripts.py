from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import json

class webhookReceiver(BaseHTTPRequestHandler):
    _bot = None

    def _handle_incoming(self, path, query_string, payload):
        path = path.split("/")
        conversation_id = path[1]
        if conversation_id is None:
            print("conversation id must be provided as part of path")
            return

        if "message=" in payload:
            payload = payload[8:].replace("+", " ")
            self._scripts_push(conversation_id, payload)
        else:
            print(payload)

        print("handler finished")

    def _scripts_push(self, conversation_id, payload):
        webhookReceiver._bot.external_send_message_parsed(conversation_id, payload)

    def do_POST(self):
        """
            receives post, handles it
        """
        print('receiving POST...')
        data_string = self.rfile.read(int(self.headers['Content-Length'])).decode('UTF-8')
        self.send_response(200)
        message = bytes('OK', 'UTF-8')
        self.send_header("Content-type", "text")
        self.send_header("Content-length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)
        print('connection closed')

        # parse requested path + query string
        _parsed = urlparse(self.path)
        path = _parsed.path
        query_string = parse_qs(_parsed.query)

        print("incoming path: {}".format(path))

        print(data_string)

        # parse incoming data
        payload = data_string
        self._handle_incoming(path, query_string, payload)
