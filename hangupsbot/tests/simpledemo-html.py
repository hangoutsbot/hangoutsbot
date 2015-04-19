# use with the simpledemo sink which is part of sinks.generic.simpledemo package
import json
import requests
url = 'https://127.0.0.1:9002/UgxcYwkNkvwAWx4Ee-Z4AaABAQ/'
payload = {"echo" : '<b>EXAMPLE</b>'}
headers = {'content-type': 'application/json'}
r = requests.post(url, data = json.dumps(payload), headers = headers, verify=False)
print(r)
