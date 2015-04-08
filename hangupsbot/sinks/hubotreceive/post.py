from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

import json

class receiver(BaseHTTPRequestHandler):
    _bot = None

    def _handle_incoming(self, path, query_string, payload):
        path = path.split("/")
        conversation_id = path[1]
        if conversation_id is None:
            print(_("conversation id must be provided as part of path"))
            return

        # send to one room, or to many? [sync_rooms support]
        broadcast_list = [conversation_id]
        sync_room_list = receiver._bot.get_config_option('sync_rooms')
        if sync_room_list:
            if conversation_id in sync_room_list:
                broadcast_list = sync_room_list

        for conversation_id in broadcast_list:
            receiver._bot.send_html_to_conversation(conversation_id, payload["message"])

    def do_POST(self):
        """
            receives post, handles it
        """
        print(_('receiving POST...'))

        content_length = 0
        if 'Content-Length' in self.headers:
            content_length = int(self.headers['Content-Length']);
        else:
            print(_("no content-length found!"))
            print(self.headers)

        data_string = self.rfile.read(content_length).decode('UTF-8')

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

        if data_string == '':
            print(_("no data was received"))
            return

        print(_("data: {}").format(data_string))

        payload = json.loads(data_string)
        self._handle_incoming(path, query_string, payload)

    def log_message(self, formate, *args):
        # disable printing to stdout/stderr for every post
        return
