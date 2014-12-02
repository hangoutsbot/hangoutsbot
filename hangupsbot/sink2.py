import asyncio
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer

def start_rpc_listener(bot, loop):
    asyncio.set_event_loop(loop)

    server = SimpleJSONRPCServer(('localhost', 4000))
    server.register_function(bot.external_send_message, 'send')
    server.register_function(bot.external_send_message_parsed, 'sendparsed')
    server.serve_forever()

if __name__ == '__main__':
    start_rpc_listener()
