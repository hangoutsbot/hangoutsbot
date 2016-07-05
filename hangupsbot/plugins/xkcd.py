import aiohttp, asyncio, io, logging, os, re, urllib.request, urllib.error
from bs4 import BeautifulSoup
import plugins

logger = logging.getLogger(__name__)

def _initialise(bot):
 plugins.register_handler(_watch_xkcd_link, type="message")

@asyncio.coroutine
def _watch_xkcd_link(bot, event, command):
  if event.user.is_self:
    return

  if " " in event.text:
    return

  if re.match("^https?://(www\.)?xkcd.com(/([0-9]+/)?)?$", event.text.lower(), re.IGNORECASE):
    url = event.text.lower()
    try:
      response = urllib.request.urlopen(url)
    except urllib.error.URLError as e:
      logger.info("Tried and failed to get the xkcd comic :(")
      logger.info(e.read())
      return

    body = response.read()
    soup = BeautifulSoup(body.decode("utf-8"), "lxml")
    comic = soup.find(src=re.compile('//imgs.xkcd.com/comics/.+'))
    alttext = comic.attrs['title']
    imgurl = comic.attrs['src']
    title = comic.attrs['alt']

    link_image = "http:{}".format(imgurl)
    filename = os.path.basename(link_image)
    r = yield from aiohttp.request('get', link_image)
    raw = yield from r.read()
    image_data = io.BytesIO(raw)
    image_id = yield from bot._client.upload_image(image_data, filename=filename)

    yield from bot.coro_send_message(event.conv, "<b><u>{}</u></b><br>{}".format(title, alttext), image_id=image_id)
