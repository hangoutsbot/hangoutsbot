"""simple send test
usage: base-send.py [-h] url content

positional arguments:
  url         url to send the data
  content     content to send, quote if it contains spaces

optional arguments:
  -h, --help  show this help message and exit

example usage:
python3 api-send.py http://127.0.0.1:9999/<CONV_ID>/ "echo hello world"
"""
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("url", help="url to send the data")
parser.add_argument("content", help="content to send, quote if it contains spaces")
args = parser.parse_args()

import json
import requests

payload = {
    'echo': args.content
}

headers = {'content-type': 'application/json'}
r = requests.post(args.url, data = json.dumps(payload), headers = headers, verify=False)

print(r)
