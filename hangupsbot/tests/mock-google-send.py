# use with the simpledemo sink which is part of sinks.generic.simpledemo package
import json
import requests
url = 'https://127.0.0.1:8002/Ugy7L_jAnik6pPUczsZ4AaABAQ/'
payload = {"message" : "HELLO FROM MOCK GOOGLE!!!"}
headers = {'content-type': 'application/json'}
r = requests.post(url, data = json.dumps(payload), headers = headers, verify=False)
print(r)
