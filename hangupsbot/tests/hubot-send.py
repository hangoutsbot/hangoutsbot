# use with the simpledemo sink which is part of sinks.generic.simpledemo package
import json
import requests
url = 'http://127.0.0.1:8080/receive/UgwuaaLQf2IPoqZDmFZ4AaABAQ'
payload = {"from" : "testuser1", "message" : "hubot time"}
headers = {'content-type': 'application/json'}
r = requests.post(url, data = json.dumps(payload), headers = headers, verify=False)
print(r)
