import logging
import hangups
import plugins
import asyncio

import googlemaps

logger = logging.getLogger(__name__)

from textblob import TextBlob
from urllib.parse import quote

def _initialise(bot):
    plugins.register_handler(_handle_message, type="message")

def _handle_message(bot, event, command):
    raw_text = " ".join(event.text.split())
    directions = ["how", "long", "take", "to", "from"]
    if all(x in raw_text.lower() for x in directions):
        yield from _getdirections(bot, event, raw_text, directions)

@asyncio.coroutine
def _getdirections(bot, event, text, type):
    logger.info("Directions from text: " + text)
    try:
        mapskey = bot.get_config_option("maps_api_key")
    except:
        logger.error("Something went wrong getting the API key. Check it and reload.")
        return
    if not mapskey.startswith("AIza"):
        logger.error("Your API key is wrong, apparently. Check it and reload.")
        return

    bicycling = ["by bicycling","via bicycling", "by cycling","via cycling", "by bike","via bike", "a bicycle", "to cycle"]
    walking = ["on foot", "by walking","via walking", "to walk", "by foot","via foot"]
    transit = ["by public transport","via public transport"]
    train = ["by train","via train"]
    bus = ["by bus","via bus"]
    subway = ["by subway", "on the subway", "by the subway", "via subway", "via the subway"]
    tram = ["via tram", "via light rail","by tram", "by light rail","on the tram", "on the light rail"]

    try:
        regionbias = bot.get_config_option("directions_geobias")
    except:
        regionbias = ""

    routeMode = "driving"
    transitMode = ""

    if any(x in text for x in transit):
        routeMode = "transit"
        for f in transit:
            text = text.replace(f, "")
    elif any(x in text for x in bicycling):
        routeMode = "bicycling"
        for f in bicycling:
            text = text.replace(f, "")
    elif any(x in text for x in walking):
        routeMode = "walking"
        for f in walking:
            text = text.replace(f, "")
    elif any(x in text for x in train):
        routeMode = "transit"
        transitMode = "train"
        for f in train:
            text = text.replace(f, "")
    elif any(x in text for x in bus):
        routeMode = "transit"
        transitMode = "bus"
        for f in bus:
            text = text.replace(f, "")
    elif any(x in text for x in subway):
        routeMode = "transit"
        transitMode = "subway"
        for f in subway:
            text = text.replace(f, "")
    elif any(x in text for x in tram):
        routeMode = "transit"
        transitMode = "tram"
        for f in tram:
            text = text.replace(f, "")
    
    logger.info("text:" + text)
    text = TextBlob(text)
    for s in text.sentences:
        logger.info(s)
        if all(x in s.lower() for x in type):
            dFrom = s.lower().words.index(type[-1])
            dTo = [i for i, x in enumerate(s.lower().words) if x == type[-2]][-1]

            if dFrom + 1 < dTo:
                origin = " ".join(s.words[dFrom + 1:dTo])
                destination = " ".join(s.words[dTo + 1:])
            elif dTo + 1 < dFrom:
                destination = " ".join(s.words[dTo + 1:dFrom])
                origin = " ".join(s.words[dFrom + 1:])

            gmaps = googlemaps.Client(key=mapskey)

            dirs = gmaps.directions(origin, destination, mode=routeMode, region=regionbias, transit_mode=transitMode)

            logger.info("origin/destination/mode/region/transit_mode:" + "/" + origin + "/"  + destination + "/" + routeMode + "/" + regionbias + "/" + transitMode)
 
            try:
                dirs1 = dirs[0]
                dirlegs = dirs1["legs"]
                dirleg = dirlegs[0]
                duration = dirleg["duration"]
                time = duration["text"]
                startAddr = dirleg["start_address"]
                endAddr = dirleg["end_address"]
                mapsUrl = "https://www.google.com/maps?f=d&saddr=" + quote(startAddr) + "&daddr=" + quote(endAddr)
                routeUrlParams = {"walking":"w","transit":"r","bicycling":"b"}
                logger.info(dirs1)
                logger.info(dirleg)
                logger.info(dirs)
                if routeMode: mapsUrl = mapsUrl + "&dirflg=" + routeUrlParams[routeMode]
                yield from bot.coro_send_message(event.conv, "Looks like it'll take you " + time + " to get from " + startAddr + " to " + endAddr + '. [<a href="' + mapsUrl + '" >maps</a>]')
            except IndexError:
                logger.error(dirs)
