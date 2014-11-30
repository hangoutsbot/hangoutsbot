from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer

def hello(str):
    print('hello', str)

def start_rpc_listener():
    server = SimpleJSONRPCServer(('localhost', 4000))
    server.register_function(hello)
    server.serve_forever()

if __name__ == '__main__':
    start_rpc_listener()
