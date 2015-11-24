import aiohttp, asyncio, logging, os, random, urllib.request

from bs4 import BeautifulSoup

import hangups

import plugins


logger = logging.getLogger(__name__)


_externals = { "running": False }


def _initialise(bot):
    plugins.register_user_command(["meme"])


@asyncio.coroutine
def _retrieve(url, css_selector, attribute):
    logger.debug("_retrieve(): getting {}".format(url))
    html_request = yield from aiohttp.request('get', url)
    html = yield from html_request.read()
    soup = BeautifulSoup(str(html, 'utf-8'), 'html.parser')
    links = []
    for link in soup.select(css_selector):
        links.append(link.get(attribute))
    return links


def meme(bot, event, *args):
    """Searches for a meme related to <something>;
    grabs a random meme when none provided"""
    if _externals["running"]:
        yield from bot.coro_send_message(event.conv_id, "<i>busy, give me a moment...</i>")
        return

    _externals["running"] = True

    try:
        parameters = list(args)
        if len(parameters) == 0:
            parameters.append("robot")

        links = yield from _retrieve("http://memegenerator.net/memes/search?q=" + "+".join(parameters), ".item_medium_small > a", "href")
        links = yield from _retrieve("http://memegenerator.net" + random.choice(links), ".item_medium_small > a", "href")

        instance_link = "http://memegenerator.net" + random.choice(links)
        links = yield from _retrieve(instance_link, ".instance_large > img", "src")

        if len(links) > 0:
            jpg_link = links.pop()

            image_data = urllib.request.urlopen(jpg_link)
            filename = os.path.basename(jpg_link)

            legacy_segments = [hangups.ChatMessageSegment(instance_link, hangups.SegmentType.LINK, link_target=instance_link)]

            logger.debug("uploading {} from {}".format(filename, jpg_link))
            photo_id = yield from bot._client.upload_image(image_data, filename=filename)

            yield from bot.coro_send_message(event.conv.id_, legacy_segments, image_id=photo_id)

        else:
            yield from bot.coro_send_message(event.conv_id, "<i>couldn't find a nice picture :( try again</i>")

    except Exception as e:
        yield from bot.coro_send_message(event.conv_id, "<i>couldn't find a suitable meme! try again</i>")
        logger.exception("FAILED TO RETRIEVE MEME")

    finally:
        _externals["running"] = False
