import time
import json
import base64
import io
import asyncio

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from utils import simple_parse_to_segments

class webhookReceiver(BaseHTTPRequestHandler):
    _bot = None # set externally by the hangupsbot sink loader
    sinkname = "sink"

    @asyncio.coroutine
    def process_payload(self, path, query_string, payload):
        sinkname = self.sinkname

        path = path.split("/")
        conversation_id = path[1]
        if conversation_id is None:
            print("{}: conversation id must be provided as part of path".format(sinkname))
            return

        image_id = None
        if "image" in payload:
            image_data = False
            image_filename = False
            if "base64encoded" in payload["image"]:
                raw = base64.b64decode(payload["image"]["base64encoded"])
                image_data = io.BytesIO(raw)
            if "filename" in payload["image"]:
                image_filename = payload["image"]["filename"]
            else:
                image_filename = str(int(time.time())) + ".jpg"
            print("{}: uploading image: {}".format(sinkname, image_filename))
            image_id = yield from webhookReceiver._bot._client.upload_image(image_data, filename=image_filename)

        html = ""
        if "echo" in payload:
            html = payload["echo"]
        else:
            # placeholder text
            html = "<b>hello world</b>"
        segments = simple_parse_to_segments(html)
        print("{} sending segments: {}".format(sinkname, len(segments)))

        webhookReceiver._bot.send_message_segments(conversation_id, segments, context=None, image_id=image_id)

    def do_POST(self):
        sinkname = self.sinkname

        print('{}: receiving POST...'.format(sinkname))

        data_string = self.rfile.read(int(self.headers['Content-Length'])).decode('UTF-8')
        self.send_response(200)
        message = bytes('OK', 'UTF-8')
        self.send_header("Content-type", "text")
        self.send_header("Content-length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)
        print('{}: connection closed'.format(sinkname))

        # parse requested path + query string
        _parsed = urlparse(self.path)
        path = _parsed.path
        query_string = parse_qs(_parsed.query)

        print("{}: incoming path: {}".format(sinkname, path))
        print("{}: incoming data: approx {} bytes".format(sinkname, len(data_string)))

        # parse incoming data
        payload = json.loads(data_string)

        # process the payload
        asyncio.async(self.process_payload(path, query_string, payload))
