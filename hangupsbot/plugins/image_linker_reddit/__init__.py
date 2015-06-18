"""trigger popular reddit meme images
based on the word/image list for the image linker bot on reddit
sauce: http://www.reddit.com/r/image_linker_bot/comments/2znbrg/image_suggestion_thread_20/
"""

import io
import os
import re
import random
import aiohttp

import plugins


_lookup = {}


def _initialise(bot):
    _load_all_the_things()
    plugins.register_admin_command(["redditmemeword"])
    plugins.register_handler(_scan_for_triggers)


def redditmemeword(bot, event, *args):
    if len(args) == 1:
        image_link = _get_a_link(args[0])
    bot.send_html_to_conversation(event.conv_id, "this one? {}".format(image_link))


def _scan_for_triggers(bot, event, command):
    limit = 3
    count = 0
    lctext = event.text.lower()
    image_links = []
    for trigger in _lookup:
        pattern = '\\b' + trigger + '\.(jpg|png|gif|bmp)\\b'
        if re.search(pattern, lctext):
            image_links.append(_get_a_link(trigger))
            count = count + 1
            if count >= limit:
                break

    image_links = list(set(image_links)) # make unique

    if len(image_links) > 0:
        for image_link in image_links:
            if "gfycat.com/" in image_link:
                r = yield from aiohttp.request('get', image_link)
                raw = yield from r.read()
                image_link = re.search("<a href=\"(.*?)\">\\1</a>", str(raw, 'utf-8')).group(1)
            filename = os.path.basename(image_link)
            r = yield from aiohttp.request('get', image_link)
            raw = yield from r.read()
            image_data = io.BytesIO(raw)
            print("image_linker_reddit: attempting to display: {}".format(filename))
            image_id = yield from bot._client.upload_image(image_data, filename=filename)
            bot.send_message_segments(event.conv.id_, None, image_id=image_id)


def _load_all_the_things():
    plugin_dir = os.path.dirname(os.path.realpath(__file__))
    source_file = os.path.join(plugin_dir, "sauce.txt")
    with open(source_file) as f:
        content = f.read().splitlines()
    for line in content:
        parts = line.strip("|").split('|')
        if len(parts) == 2:
            triggers, images = parts
            triggers = [x.strip() for x in triggers.split(',')]
            images = [re.search('\((.*?)\)$', x).group(1) for x in images.split(' ')]
            for trigger in triggers:
                if trigger in _lookup:
                    _lookup[trigger].extend(images)
                else:
                    _lookup[trigger] = images
    print("reddit image meme: {} trigger(s) loaded".format(len(_lookup)))


def _get_a_link(trigger):
    if trigger in _lookup:
        return random.choice(_lookup[trigger])
    return False
