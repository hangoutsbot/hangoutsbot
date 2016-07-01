import asyncio, functools, logging, os, ssl

from aiohttp import web
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from utils import class_from_name

from sinks.base_bot_request_handler import BaseBotRequestHandler, AsyncRequestHandler

import threadmanager

from plugins import tracking


logger = logging.getLogger(__name__)

aiohttp_servers = []


def start(bot):
    shared_loop = asyncio.get_event_loop()

    jsonrpc_sinks = bot.get_config_option('jsonrpc')
    itemNo = -1

    threadcount = 0
    aiohttpcount = 0

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

                certfile = sinkConfig.get("certfile")
                if certfile and not os.path.isfile(certfile):
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

            if issubclass(handler_class, AsyncRequestHandler):
                aiohttp_start(
                    bot,
                    name,
                    port,
                    certfile,
                    handler_class,
                    "json-rpc")

                aiohttpcount = aiohttpcount + 1

            else:
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
        logger.info("{} threaded listener(s)".format(threadcount))

    if aiohttpcount:
        logger.info("{} aiohttp web listener(s)".format(aiohttpcount))


def start_listening(bot=None, loop=None, name="", port=8000, certfile=None, webhookReceiver=BaseHTTPRequestHandler, friendlyName="UNKNOWN"):
    if loop:
        asyncio.set_event_loop(loop)

    if bot:
        webhookReceiver._bot = bot

    try:
        httpd = HTTPServer((name, port), webhookReceiver)

        if certfile:
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



def aiohttp_start(bot, name, port, certfile, RequestHandlerClass, group, callback=None):
    RequestHandler = RequestHandlerClass(bot)

    app = web.Application()

    handler = app.make_handler()
    RequestHandler.addroutes(app.router)

    if certfile:
        sslcontext = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        sslcontext.load_cert_chain(certfile)
    else:
        sslcontext = None

    loop = asyncio.get_event_loop()
    server = loop.create_server(handler, name, port, ssl=sslcontext)

    asyncio.async(server).add_done_callback(functools.partial( aiohttp_started,
                                                               handler=handler,
                                                               app=app,
                                                               group=group,
                                                               callback=callback ))

    tracking.register_aiohttp_web(group)

def aiohttp_started(future, handler, app, group, callback=None):
    server = future.result()
    constructors = (server, handler, app, group)

    aiohttp_servers.append(constructors)

    logger.info("aiohttp: {} on {}".format(group, server.sockets[0].getsockname()))

    if callback:
        callback(constructors)

def aiohttp_list(groups):
    if isinstance(groups, str):
        groups = [groups]

    filtered = []
    for constructors in aiohttp_servers:
        if constructors[3] in groups:
            filtered.append(constructors)

    return filtered

@asyncio.coroutine
def aiohttp_terminate(groups):
    removed = []
    for constructors in aiohttp_list(groups):
        [server, handler, app, group] = constructors

        yield from handler.finish_connections(1.0)
        server.close()
        yield from server.wait_closed()
        yield from app.finish()

        logger.info("aiohttp: terminating {} {}".format(constructors[3], constructors))
        removed.append(constructors)

    for constructors in removed:
        aiohttp_servers.remove(constructors)
