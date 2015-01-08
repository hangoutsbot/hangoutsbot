# use with the simpledemo sink which is part of sinks.generic.simpledemo package
import json
import requests
url = 'https://127.0.0.1:9001/UgwuaaLQf2IPoqZDmFZ4AaABAQ/'
payload = {"echo" : '1: <a href="https://www.google.com/">embedded</a> | 2: <a href="https://www.google.com/">www.google.com</a> | 3: https://www.google.com | 4: <a href="https://www.google.com">https://www.google.com</a> | 5: <a href="https://gitlab.sabah.io/eol/mogunsamang/commit/450b444d5aaa494b2e861ad4db6803496a995d80">gitlab commit</a>'}
headers = {'content-type': 'application/json'}
r = requests.post(url, data = json.dumps(payload), headers = headers, verify=False)
print(r)
