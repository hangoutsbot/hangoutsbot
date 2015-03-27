from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import json
import requests

import asyncio
import hangups

def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["lifx"])
    Handlers.register_user_command([])
    return []

def lifx(bot, event, *args):
    """ Play with your LIFX bulbs! """
    url = 'https://api.lifx.com/v1beta1/lights/'
    data = '{"query":{"bool":{"must":[{"text":{"record.document":"SOME_JOURNAL"}},{"text":{"record.articleTitle":"farmers"}}],"must_not":[],"should":[]}},"from":0,"size":50,"sort":[],"facets":{}}'
    response = requests.get(url, data=data)
