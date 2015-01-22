from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

import json

class receiver(BaseHTTPRequestHandler):
    _bot = None

    def _handle_incoming(self, path, query_string, payload):
        path = path.split("/")
        conversation_id = path[1]
        if conversation_id is None:
            print("conversation id must be provided as part of path") 
            return

        receiver._bot.external_send_message_parsed(conversation_id, payload)

    def do_POST(self):
        """
            receives post, handles it
        """
        print('receiving POST...')

        content_length = 0
        if 'Content-Length' in self.headers:
            content_length = int(self.headers['Content-Length']);
        else:
            print("no content-length found!")
            print(self.headers)

        data_string = self.rfile.read(content_length).decode('UTF-8')

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

        if data_string == '':
            print("no data was received")
            return

        # hubot adapter returns data message=<uri-encoded>
        data_string = unquote(data_string[8:])

        self._handle_incoming(path, query_string, data_string)

    def log_message(self, formate, *args):
        # disable printing to stdout/stderr for every post
        return