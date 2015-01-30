import ssl
import asyncio

from http.server import BaseHTTPRequestHandler, HTTPServer

def start_listening(bot=None, loop=None, name="", port=8000, certfile=None, webhookReceiver=BaseHTTPRequestHandler, friendlyName="UNKNOWN"):
    if loop:
        asyncio.set_event_loop(loop)

    if bot:
        webhookReceiver._bot = bot

    try:
        httpd = HTTPServer((name, port), webhookReceiver)

        httpd.socket = ssl.wrap_socket(
          httpd.socket, 
          certfile=certfile, 
          server_side=True)

        sa = httpd.socket.getsockname()
        print("listener: {} : sink on {}, port {}...".format(friendlyName, sa[0], sa[1]))

        httpd.serve_forever()
    except IOError:
        # do not run sink without https!
        print("listener: {} : pem file possibly missing or broken (== '{}')".format(friendlyName, certfile))
        httpd.socket.close()
    except KeyboardInterrupt:
        httpd.socket.close()