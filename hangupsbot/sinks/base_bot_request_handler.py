import time
import json
import base64
import io
import asyncio
import logging

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from utils import simple_parse_to_segments

class BaseBotRequestHandler(BaseHTTPRequestHandler):
    _bot = None # set externally by the hangupsbot sink loader
    sinkname = "UNKNOWN"

    def __init__(self, *args):
        self.sinkname = self.__class__.__name__
        BaseHTTPRequestHandler.__init__(self, *args)


    def do_POST(self):
        """handle incoming POST request
        acquire the path, any query string (?abc=xyz), sent content
        """
        print('{}: receiving POST...'.format(self.sinkname))

        content = self.rfile.read(int(self.headers['Content-Length'])).decode('UTF-8')
        self.send_response(200)
        message = bytes('OK', 'UTF-8')
        self.send_header("Content-type", "text")
        self.send_header("Content-length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)
        print('{}: connection closed'.format(self.sinkname))

        # parse requested path + query string
        _parsed = urlparse(self.path)
        path = _parsed.path
        query_string = parse_qs(_parsed.query)

        print("{}: incoming: {} {} {} bytes".format(self.sinkname, path, query_string, len(content)))

        # process the payload
        asyncio.async(self.process_request(path, query_string, content))


    @asyncio.coroutine
    def process_request(self, path, query_string, content):
        """default handler for incoming request
        path should contain a conversation id e.g. http://localhost/XXXXXXXXXXX/
        content is a valid json string with keys:
            echo                html string
            image 
                base64encoded   base64-encoded image data
                filename        optional filename
        """
        # parse incoming data
        payload = json.loads(content)

        path = path.split("/")
        conversation_id = path[1]
        if conversation_id is None:
            print("{}: conversation id must be provided as part of path".format(self.sinkname))
            return

        html = None
        if "echo" in payload:
            html = payload["echo"]

        if "image" in payload:
            image_data = False
            image_filename = False
            if "base64encoded" in payload["image"]:
                raw = base64.b64decode(payload["image"]["base64encoded"])
                image_data = io.BytesIO(raw)
            if "filename" in payload["image"]:
                image_filename = payload["image"]["filename"]

        if not html and not image_data:
            print("{}: nothing to send".format(self.sinkname))
            return

        yield from self.send_data(conversation_id, html, image_data=image_data, image_filename=image_filename)


    @asyncio.coroutine
    def send_data(self, conversation_id, html, image_data=None, image_filename=None):
        """sends html and/or image to a conversation
        image_filename is optional, defaults to <timestamp>.jpg if not defined
        """
        image_id = None
        if image_data:
            if not image_filename:
                image_filename = str(int(time.time())) + ".jpg"
            image_id = yield from self._bot._client.upload_image(image_data, filename=image_filename)

        if not html and not image_id:
            print("{}: nothing to send".format(self.sinkname))
            return

        segments = simple_parse_to_segments(html)
        print("{}: sending segments: {}".format(self.sinkname, len(segments)))

        self._bot.send_message_segments(conversation_id, segments, context=None, image_id=image_id)


    def log_error(self, format_string, *args):
        logging.error("{} - {} {}".format(self.sinkname, self.address_string(), format_string%args))

    def log_message(self, format_string, *args):
        logging.info("{} - {} {}".format(self.sinkname, self.address_string(), format_string%args))