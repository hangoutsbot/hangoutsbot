import jsonrpclib

server = jsonrpclib.ServerProxy('http://localhost:4000')
server.sendparsed(conversation_id = 'UgwuaaLQf2IPoqZDmFZ4AaABAQ', 
                  html = 'hello world<br /><b>it <u>works!</u></b>')
server('close')()
