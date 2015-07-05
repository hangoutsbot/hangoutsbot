import logging

from threading import Thread

import ssl
import asyncio

from http.server import BaseHTTPRequestHandler, HTTPServer
from utils import class_from_name

from sinks.base_bot_request_handler import BaseBotRequestHandler


def start(bot, shared_loop):
    jsonrpc_sinks = bot.get_config_option('jsonrpc')
    itemNo = -1
    threads = []

    if isinstance(jsonrpc_sinks, list):
        for sinkConfig in jsonrpc_sinks:
            itemNo += 1

            try:
                module = sinkConfig["module"].split(".")
                if len(module) < 3:
                    print("config.jsonrpc[{}].module should have at least 3 packages {}".format(itemNo, module))
                    continue

                module_name = ".".join(module[0:-1])
                class_name = ".".join(module[-1:])
                if not module_name or not class_name:
                    print(_("config.jsonrpc[{}].module must be a valid package name").format(itemNo))
                    continue

                certfile = sinkConfig["certfile"]
                if not certfile:
                    print(_("config.jsonrpc[{}].certfile must be configured").format(itemNo))
                    continue

                name = sinkConfig["name"]
                port = sinkConfig["port"]
            except KeyError as e:
                print(_("config.jsonrpc[{}] missing keyword").format(itemNo), e)
                continue

            try:
                handler_class = class_from_name(module_name, class_name)
            except AttributeError as e:
                logging.exception(e)
                print("could not identify sink: {} {}".format(module_name, class_name))
                continue

            # start up rpc listener in a separate thread
            print(_("_start_sinks(): {}").format(module))
            t = Thread(target=start_listening, args=(
              bot,
              shared_loop,
              name,
              port,
              certfile,
              handler_class,
              module_name))

            t.daemon = True
            t.start()

            threads.append(t)

    message = _("_start_sinks(): {} sink thread(s) started").format(len(threads))
    logging.info(message)

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
        print(_("listener: {} : sink on {}, port {}...").format(friendlyName, sa[0], sa[1]))

        httpd.serve_forever()
    except IOError:
        # do not run sink without https!
        print(_("listener: {} : pem file possibly missing or broken (== '{}')").format(friendlyName, certfile))
        httpd.socket.close()
    except OSError as e:
        # Could not connect to HTTPServer!
        print(_("listener: {} : requested access could not be assigned. Is something else using that port? (== '{}:{}')").format(friendlyName, name, port))
    except KeyboardInterrupt:
        httpd.socket.close()
