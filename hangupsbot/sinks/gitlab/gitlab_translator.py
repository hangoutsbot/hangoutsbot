from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import jsonrpclib

hangouts_server = jsonrpclib.ServerProxy('http://localhost:4000')

class webhookReceiver(BaseHTTPRequestHandler):

    def _package_push(self, json):
        text = '<b>{}</b> has pushed {} commit(s)<br />'.format(
          json["user_name"], 
          json["total_commits_count"],
          json["repository"]["url"])

        for commit in json["commits"]:
            text += '* <i>{}</i> by <b>{}</b> @ <a href="{}">{}</a><br />'.format(
              commit["message"],
              commit["author"]["name"],
              commit["url"],
              commit["timestamp"])

        hangouts_server.sendparsed(
          conversation_id = 'UgwuaaLQf2IPoqZDmFZ4AaABAQ',
          html = text)

    def do_POST(self):
        """
            receives post, handles it
        """
        data_string = self.rfile.read(int(self.headers['Content-Length'])).decode('UTF-8')
        self.send_response(200)
        message = bytes('OK', 'UTF-8')
        self.send_header("Content-type", "text")
        self.send_header("Content-length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)

        print('gitlab connection should be closed now.')

        # parse data
        payload = json.loads(data_string)
        text = json.dumps(payload)
        print(text)

        try:
            object_kind = payload["object_kind"]
        except KeyError:
            object_kind = 'push'

        if object_kind == 'push':
            self._package_push(payload)
        else:
            print(payload)

    def log_message(self, formate, *args):
        """
            disable printing to stdout/stderr for every post
        """
        return


def main():
    """
        the main event.
    """
    try:
        server = HTTPServer(('', 8000), webhookReceiver)
        server.serve_forever()
    except KeyboardInterrupt:
        hangouts_server('close')()
        server.socket.close()

if __name__ == '__main__':
    main()