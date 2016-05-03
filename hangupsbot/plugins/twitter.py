import aiohttp, asyncio, io, logging, os, re, urllib.request
from bs4 import BeautifulSoup
import plugins

logger = logging.getLogger(__name__)

def _initialise(bot):
 plugins.register_handler(_watch_twitter_link, type="message")

@asyncio.coroutine
def _watch_twitter_link(bot, event, command):
  if event.user.is_self:
    return

  if " " in event.text:
    return

  if re.match("^(https?://)?(www\.)?twitter.com/[a-zA-Z0-9_]{1,15}/status/[0-9]+$", event.text.lower(), re.IGNORECASE):
    url = event.text.lower()
    try:
      response = urllib.request.urlopen(url)
    except URLError as e:
      logger.info("Tried and failed to get the twitter status text:(")
      logger.info(e.read())
      return

    body = response.read()
    soup = BeautifulSoup(body.decode("utf-8"), "lxml")
    twhandle = soup.title.text.split(" on Twitter: ")[0].strip()
    tweet = re.sub(r"#([a-zA-Z0-9]*)",r"<a href='https://twitter.com/hashtag/\1'>#\1</a>", soup.title.text.split(" on Twitter: ")[1].strip())
    yield from bot.coro_send_message(event.conv, "<b><a href='{}'>@{}</a></b>: {}".format("https://twitter.com/{}".format(twhandle), twhandle, tweet))
