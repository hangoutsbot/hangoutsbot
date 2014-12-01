import asyncio
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer

def start_rpc_listener(bot, loop):
    print("started listening")

    asyncio.set_event_loop(loop)

    server = SimpleJSONRPCServer(('localhost', 4000))
    server.register_function(lambda: bot.rpc_list_conversations(), 'list')
    server.register_function(lambda: bot.rpc_send_message(), 'testsend')
    server.serve_forever()

if __name__ == '__main__':
    start_rpc_listener()
