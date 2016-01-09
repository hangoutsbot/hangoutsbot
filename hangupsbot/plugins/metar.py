import logging
import plugins
import requests
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

def _initialize(bot):
    plugins.register_user_command(['metar'])

def metar(bot, event, *args):
    """
    Looks up the most recent METAR weather report for the supplied ICAO airport code.
        <b>/bot metar <ICAO airport code></b>
    ICAO Airport Codes: https://en.wikipedia.org/wiki/International_Civil_Aviation_Organization_airport_code
    METAR source: http://aviationweather.gov
    """
    code = ''.join(args).strip()
    if not code:
        yield from bot.coro_send_message(event.conv_id, "You need to enter the ICAO airport code you wish the look up, https://en.wikipedia.org/wiki/International_Civil_Aviation_Organization_airport_code .")
        return
    
    api_url = "http://aviationweather.gov/adds/dataserver_current/httpparam?dataSource=metars&requestType=retrieve&format=xml&hoursBeforeNow=3&mostRecent=true&stationString="+code
    r= requests.get(api_url)
    
    try:
        root = ElementTree.fromstring(r.content)        
        raw = root.findall('data/METAR/raw_text')
        if not raw or len(raw) == 0:
            yield from bot.coro_send_message(event.conv_id, "The response did not contain METAR information, check the ICAO airport code and try again.")
            return
        yield from bot.coro_send_message(event.conv_id, raw[0].text)        
        
    except Exception as e:
        logger.info("METAR Error: {}".format(e))
        yield from bot.coro_send_message(event.conv_id, "There was an error retrieving the METAR information.")