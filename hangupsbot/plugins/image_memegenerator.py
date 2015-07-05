import os
import random
import asyncio
import aiohttp
import hangups
import urllib.request

from bs4 import BeautifulSoup

import plugins


_externals = { "running": False }


def _initialise(bot):
    plugins.register_user_command(["meme"])


@asyncio.coroutine
def _retrieve(url, css_selector, attribute):
    print("meme._retrieve(): getting {}".format(url))
    html_request = yield from aiohttp.request('get', url)
    html = yield from html_request.read()
    soup = BeautifulSoup(str(html, 'utf-8'))
    links = []
    for link in soup.select(css_selector):
        links.append(link.get(attribute))
    return links


def meme(bot, event, *args):
    if _externals["running"]:
        bot.send_html_to_conversation(event.conv_id, "<i>busy, give me a moment...</i>")
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

            print("meme(): uploading {} from {}".format(filename, jpg_link))
            photo_id = yield from bot._client.upload_image(image_data, filename=filename)

            bot.send_message_segments(event.conv.id_, legacy_segments, image_id=photo_id)

        else:
            bot.send_html_to_conversation(event.conv_id, "<i>couldn't find a nice picture :( try again</i>")
    except Exception as e:
        bot.send_html_to_conversation(event.conv_id, "<i>couldn't find a suitable meme! try again</i>")
        print("{}".format(e))
    finally:
        _externals["running"] = False
