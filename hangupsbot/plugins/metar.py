"""
Looks up the most recent METAR/TAF weather report for the supplied ICAO airport code.
        <b>/bot metar <ICAO airport code></b>
        <b>/bot taf <ICAO airport code></b>

ICAO Airport Codes: https://en.wikipedia.org/wiki/International_Civil_Aviation_Organization_airport_code
METAR source: http://aviationweather.gov
"""

import logging
import plugins
import requests
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

def _initialize(bot):
    plugins.register_user_command(['metar','taf'])

def _api_lookup(type, iaco):
    api_url = "http://aviationweather.gov/adds/dataserver_current/httpparam?dataSource={0}s&requestType=retrieve&format=xml&hoursBeforeNow=3&mostRecent=true&stationString={1}".format(type, iaco)
    r= requests.get(api_url)
    try:
        root = ElementTree.fromstring(r.content)
        raw = root.findall('data/{}/raw_text'.format(type))
    except ElementTree.ParseError as e:
        logger.info("METAR Error: {}".format(e))
        return None
    return raw

def metar(bot, event, *args):
    """Display the current METAR weather report for the supplied ICAO airport code.
<b>/bot metar <ICAO airport code></b>
ICAO Airport Codes: https://en.wikipedia.org/wiki/International_Civil_Aviation_Organization_airport_code
METAR source: http://aviationweather.gov"""
    code = ''.join(args).strip()
    if not code:
        yield from bot.coro_send_message(event.conv_id, "You need to enter the ICAO airport code you wish the look up, https://en.wikipedia.org/wiki/International_Civil_Aviation_Organization_airport_code .")
        return

    data = _api_lookup('METAR',code)

    if data is None:
        yield from bot.coro_send_message(event.conv_id, "There was an error retrieving the METAR information.")
    elif not data or len(data) == 0:
        yield from bot.coro_send_message(event.conv_id, "The response did not contain METAR information, check the ICAO airport code and try again.")
    else:
        yield from bot.coro_send_message(event.conv_id, data[0].text)

def taf(bot, event, *args):
    """Looks up the most recent TAF weather forecast for the supplied ICAO airport code.
<b>/bot taf <ICAO airport code></b>
ICAO Airport Codes: https://en.wikipedia.org/wiki/International_Civil_Aviation_Organization_airport_code
TAF source: http://aviationweather.gov"""

    code = ''.join(args).strip()
    if not code:
        yield from bot.coro_send_message(event.conv_id, "You need to enter the ICAO airport code you wish the look up, https://en.wikipedia.org/wiki/International_Civil_Aviation_Organization_airport_code .")
        return

    data = _api_lookup('TAF',code)

    if data is None:
        yield from bot.coro_send_message(event.conv_id, "There was an error retrieving the TAF information.")
    elif not data or len(data) == 0:
        yield from bot.coro_send_message(event.conv_id, "The response did not contain TAF information, check the ICAO airport code and try again.")
    else:
        yield from bot.coro_send_message(event.conv_id, data[0].text)
