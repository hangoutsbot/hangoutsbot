import os
import hangups

from hangups.ui.utils import get_conv_name

import json
import requests

class sender():
    _bot = None
    _config = None

    def init():
        if "HUBOT_URL" not in sender._config:
            print("cannot initalise: config.hooks[].HUBOT_URL not provided")
            return False

        return True

    def on_chat_message(event):
        if event.user.is_self:
            # don't send my own messages
            return

        event_timestamp = event.timestamp

        conversation_id = event.conv_id
        conversation_name = get_conv_name(event.conv)
        conversation_text = event.text

        user_full_name = event.user.full_name
        user_id = event.user_id

        url = sender._config["HUBOT_URL"] + conversation_id
        payload = {"from" : str(user_id.chat_id), "message" : conversation_text}
        headers = {'content-type': 'application/json'}
        r = requests.post(url, data = json.dumps(payload), headers = headers, verify=False)