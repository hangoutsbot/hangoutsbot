import aiohttp, asyncio, io, logging, os, re, urllib.request, json, datetime
from TwitterAPI import TwitterAPI
from bs4 import BeautifulSoup
import plugins

logger = logging.getLogger(__name__)
def prettydate(diff):
    s = diff.seconds
    if diff.days > 7 or diff.days < 0:
        return d.strftime('%d %b %y')
    elif diff.days == 1:
        return '1 day ago'
    elif diff.days > 1:
        return '{} days ago'.format(diff.days)
    elif s <= 1:
        return 'just now'
    elif s < 60:
        return '{} seconds ago'.format(s)
    elif s < 120:
        return '1 minute ago'
    elif s < 3600:
        return '{} minutes ago'.format(round(s/60),1)
    elif s < 7200:
        return '1 hour ago'
    else:
        return '{} hours ago'.format(round(s/3600),1)

def _initialise(bot):
  plugins.register_admin_command(["twitterkey", "twittersecret", 'twitterconfig'])
  plugins.register_handler(_watch_twitter_link, type="message")

def twittersecret(bot, event, secret):
  '''Set your Twitter API Secret. Get one from https://apps.twitter.com/app'''
  if not bot.memory.get_by_path(['twitter']):
    bot.memory.set_by_path(['twitter'], {})

  bot.memory.set_by_path(['twitter','secret'],secret)
  yield from bot.coro_send_message(event.conv, "Twitter API secret set to <b>{}</b>.".format(secret))

def twitterkey(bot, event, key):
  '''Set your Twitter API Key. Get one from https://apps.twitter.com/'''
  if not bot.memory.get_by_path(['twitter']):
    bot.memory.set_by_path(['twitter'], {})

  bot.memory.set_by_path(['twitter','key'],key)
  yield from bot.coro_send_message(event.conv, "Twitter API key set to <b>{}</b>.".format(key))

def twitterconfig(bot, event):
  '''Get your Twitter credentials. Remember that these are meant to be kept secret!'''

  if not bot.memory.exists(['twitter']):
    bot.memory.set_by_path(['twitter'], {})
  if not bot.memory.exists(['twitter', 'key']):
    bot.memory.set_by_path(['twitter', 'key'], "")
  if not bot.memory.exists(['twitter', 'secret']):
    bot.memory.set_by_path(['twitter', 'secret'], "")
  
  yield from bot.coro_send_message(event.conv, "<b>API key:</b> {}<br><b>API secret:</b> {}".format(bot.memory.get_by_path(['twitter','key']), bot.memory.get_by_path(['twitter', 'secret'])))

@asyncio.coroutine
def _watch_twitter_link(bot, event, command):
  if event.user.is_self:
    return

  if " " in event.text:
    return
    
  if not re.match("^https?://(www\.)?twitter.com/[a-zA-Z0-9_]{1,15}/status/[0-9]+$", event.text, re.IGNORECASE):
    return

  try:
    key = bot.memory.get_by_path(['twitter', 'key'])
    secret = bot.memory.get_by_path(['twitter', 'secret'])
    tweet_id = re.match(r".+/(\d+)", event.text).group(1)
    api = TwitterAPI(key, secret, auth_type="oAuth2")
    tweet = json.loads(api.request('statuses/show/:{}'.format(tweet_id)).text)
    text = re.sub(r'(\W)@(\w{1,15})(\W)', r'\1<a href="https://twitter.com/\2">@\2</a>\3' ,tweet['text'])
    text = re.sub(r'(\W)#(\w{1,15})(\W)', r'\1<a href="https://twitter.com/hashtag/\2">#\2</a>\3', text)
    time = tweet['created_at']
    timeago = prettydate(datetime.datetime.now(tz=datetime.timezone.utc) - datetime.datetime.strptime(time, '%a %b %d %H:%M:%S %z %Y'))
    logger.info(timeago)
    username = tweet['user']['name']
    twhandle = tweet['user']['screen_name']
    userurl = "https://twitter.com/intent/user?user_id={}".format(tweet['user']['id'])
    message = "<b><u><a href='{}'>@{}</a> ({})</u></b>: {} <i>{}</i>".format(userurl, twhandle, username, text, timeago)
    try:
      images = tweet['extended_entities']['media']
      for image in images:
        if image['type'] == 'photo':
          imagelink = image['media_url']
          filename = os.path.basename(imagelink)
          r = yield from aiohttp.request('get',imagelink)
          raw = yield from r.read()
          image_data = io.BytesIO(raw)
          image_id = yield from bot._client.upload_image(image_data, filename=filename)
          yield from bot.coro_send_message(event.conv.id_, None, image_id=image_id)

    except KeyError:
      pass

    yield from bot.coro_send_message(event.conv, message)
  except:
    url = event.text.lower()
    try:
      response = urllib.request.urlopen(url)
    except URLError as e:
      logger.info("Tried and failed to get the twitter status text:(")
      logger.info(e.read())
      return

    username = re.match(r".+twitter\.com/([a-zA-Z0-9_]+)/", url).group(1)
    body = response.read()
    soup = BeautifulSoup(body.decode("utf-8"), "lxml")
    twhandle = soup.title.text.split(" on Twitter: ")[0].strip()
    tweet = re.sub(r"#([a-zA-Z0-9]*)",r"<a href='https://twitter.com/hashtag/\1'>#\1</a>", soup.title.text.split(" on Twitter: ")[1].strip())
    message = "<b><a href='{}'>@{}</a> [{}]</b>: {}".format("https://twitter.com/{}".format(username), username, twhandle, tweet)
    yield from bot.coro_send_message(event.conv, message)
