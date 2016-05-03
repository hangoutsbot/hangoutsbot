import hangups, plugins, asyncio, logging, datetime
import urllib.request, urllib.parse
import json
import aiohttp, os, io

logger = logging.getLogger(__name__)

def _initialise(bot):
  plugins.register_admin_command(["foursquareid", "foursquaresecret"])
  plugins.register_user_command(['foursquare'])

@asyncio.coroutine
def foursquareid(bot, event, clid):
  '''Set the Foursquare API key for the bot - get one from https://foursquare.com/oauth'''
  if not bot.memory.exists(["foursquare"]):
    bot.memory.set_by_path(["foursquare"],{})

  if not bot.memory.exists(["foursquare"]):
    bot.memory.set_by_path(["foursquare","id"],{})

  bot.memory.set_by_path(["foursquare", "id"], clid)
  yield from bot.coro_send_message(event.conv, "Foursquare client id set to {}".format(clid))
  return

@asyncio.coroutine
def foursquaresecret(bot, event, secret):
  '''Set the Foursquare client secret for your bot - get it from https://foursquare.com/oauth'''
  if not bot.memory.exists(["foursquare"]):
    bot.memory.set_by_path(["foursquare"],{})

  if not bot.memory.exists(["foursquare"]):
    bot.memory.set_by_path(["foursquare", "secret"],{})

  bot.memory.set_by_path(["foursquare","secret"],secret)
  yield from bot.coro_send_message(event.conv, "Foursquare client secret set to {}".format(secret))
  return

def getplaces(location, clid, secret, section=None):
  url = "https://api.foursquare.com/v2/venues/explore?client_id={}&client_secret={}&limit=10&v=20160503&near={}".format(clid, secret, location)
  types = ["food", "drinks", "coffee", "shops", "arts", "outdoors", "sights", "trending", "specials"]
  if section in types:
    url = url + "&section={}".format(section)
  elif section == None:
    pass
  else:
    return None

  try:
    req = urllib.request.urlopen(url)
  except urllib.error.URLError as e:
    logger.info(e.reason)
    logger.info("URL: {}".format(url))
    logger.info("CLIENT_ID: {}".format(clid))
    logger.info("CLIENT_SECRET: {}".format(secret))
    return "<i><b>Foursquare Error</b>: {}</i>".format(json.loads(e.read().decode("utf8"))['meta']['errorDetail'])
  data = json.loads(req.read().decode("utf-8"))

  if section in types:
    places = ["Showing {} places near {}.<br>".format(section, data['response']['geocode']['displayString'])]
  else:
    places = ["Showing places near {}.<br>".format(data['response']['geocode']['displayString'])]
  for location in data['response']['groups'][0]['items']:
    mapsurl = "http://maps.google.com/maps?q={},{}".format(location['venue']['location']['lat'], location['venue']['location']['lng'])
    places.append("<b><u><a href='{}'>{}</a></b></u> (<a href='{}'>maps</a>)<br>Score: {}/10 ({})".format(mapsurl, location['venue']["name"], "http://foursquare.com/v/{}".format(location['venue']['id']), location['venue']['rating'], location['venue']['ratingSignals']))

  response = "<br>".join(places)
  return response
  

@asyncio.coroutine
def foursquare(bot, event,*args):
  '''Explore places near you with Foursquare!
<b>/bot foursquare <location></b>: Display up to 10 of the recommended places near the specified location.
<b>/bot foursquare [type] <location></b>: Display up to 10 places near the provided location of the type specified. <i>Valid types: food, drinks, coffee, shops, arts, outdoors, sights, trending, specials</i>'''
  if len(args) == 0:
    return

  try:
    clid = bot.memory.get_by_path(["foursquare", "id"])
    secret = bot.memory.get_by_path(["foursquare", "secret"])
  except:
    yield from bot.coro_send_message(event.conv, "Something went wrong - make sure the Foursquare plugin is correctly configured.")
    return

  types = ["food", "drinks", "coffee", "shops", "arts", "outdoors", "sights", "trending", "specials"]
  if args[0] in types:
    places = getplaces(urllib.parse.quote(" ".join(args[1:])), clid, secret, args[0])
  else:
    places = getplaces(urllib.parse.quote(" ".join(args)), clid, secret)
  
  if places:
    yield from bot.coro_send_message(event.conv, places)
  else:
    yield from bot.coro_send_message(event.conv, "Something went wrong.")
