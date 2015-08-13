import asyncio, logging, os, ssl

from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from utils import class_from_name

from sinks.base_bot_request_handler import BaseBotRequestHandler

import threadmanager


logger = logging.getLogger(__name__)


def start(bot):
    shared_loop = asyncio.get_event_loop()

    jsonrpc_sinks = bot.get_config_option('jsonrpc')
    itemNo = -1
    threadcount = 0

    if isinstance(jsonrpc_sinks, list):
        for sinkConfig in jsonrpc_sinks:
            itemNo += 1

            try:
                module = sinkConfig["module"].split(".")
                if len(module) < 3:
                    logger.error("config.jsonrpc[{}].module should have at least 3 packages {}".format(itemNo, module))
                    continue

                module_name = ".".join(module[0:-1])
                class_name = ".".join(module[-1:])
                if not module_name or not class_name:
                    logger.error("config.jsonrpc[{}].module must be a valid package name".format(itemNo))
                    continue

                certfile = sinkConfig["certfile"]
                if not certfile:
                    logger.error("config.jsonrpc[{}].certfile must be configured".format(itemNo))
                    continue

                if not os.path.isfile(certfile):
                    logger.error("config.jsonrpc[{}].certfile not available at {}".format(itemNo, certfile))
                    continue

                name = sinkConfig["name"]
                port = sinkConfig["port"]
            except KeyError as e:
                logger.error("config.jsonrpc[{}] missing keyword".format(itemNo), e)
                continue

            try:
                handler_class = class_from_name(module_name, class_name)

            except (AttributeError, ImportError) as e:
                logger.error("not found: {} {}".format(module_name, class_name))
                continue

            # start up rpc listener in a separate thread

            logger.debug("starting sink: {}".format(module))

            threadmanager.start_thread(start_listening, args=(
                bot,
                shared_loop,
                name,
                port,
                certfile,
                handler_class,
                module_name))

            threadcount = threadcount + 1

    if threadcount:
        logger.info("{} sink(s) from config.jsonrpc".format(threadcount))


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

        logger.info("{} : {}:{}...".format(friendlyName, sa[0], sa[1]))

        httpd.serve_forever()

    except ssl.SSLError as e:
        logger.exception("{} : {}:{}, pem file is invalid/corrupt".format(friendlyName, name, port))

    except OSError as e:
        if e.errno == 2:
            message = ".pem file is missing/unavailable"
        elif e.errno == 98:
            message = "address/port in use"
        else:
            message = e.strerror

        logger.exception("{} : {}:{}, {}".format(friendlyName, name, port, message))

        try:
            httpd.socket.close()
        except Exception as e:
            pass

    except KeyboardInterrupt:
        httpd.socket.close()
