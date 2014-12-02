import requests
import json


def main():
    url = "http://localhost:4000/"
    headers = {'content-type': 'application/json'}

    # Example echo method
    payload = {
        "method": "sendparsed",
        "params": ['UgwuaaLQf2IPoqZDmFZ4AaABAQ', 
                  ["hello ", 
                   "'''''how ", 
                   "'''are ", 
                   "''you\n", 
                   "I'm ",
                   "fine thank you...\n",
                   "http://google.com/\n",
                   "is not the same as\n",
                   "'''''http://google.com.my/\n",
                   "''[hello world](https://www.google.com.sg)",
                   "\n",
                   "\n",
                   "'nothing'"]],
        "jsonrpc": "2.0",
        "id": 0,
    }
    response = requests.post(
        url, data=json.dumps(payload), headers=headers).json()

    print(response)

if __name__ == "__main__":
    main()
