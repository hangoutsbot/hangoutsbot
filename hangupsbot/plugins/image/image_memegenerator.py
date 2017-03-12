import aiohttp, logging, json, os, random, urllib.request

import hangups

import plugins


logger = logging.getLogger(__name__)


_externals = { "running": False }


def _initialise(bot):
    plugins.register_user_command(["meme"])


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

        """public api: http://version1.api.memegenerator.net"""
        url_api = 'http://version1.api.memegenerator.net/Instances_Search?q=' + "+".join(parameters) + '&pageIndex=0&pageSize=25'

        api_request = yield from aiohttp.request('get', url_api)
        json_results = yield from api_request.read()
        results = json.loads(str(json_results, 'utf-8'))

        if len(results['result']) > 0:
            instanceImageUrl = random.choice(results['result'])['instanceImageUrl']

            image_data = urllib.request.urlopen(instanceImageUrl)
            filename = os.path.basename(instanceImageUrl)
            legacy_segments = [hangups.ChatMessageSegment( instanceImageUrl,
                                                           hangups.SegmentType.LINK,
                                                           link_target = instanceImageUrl )]
            logger.debug("uploading {} from {}".format(filename, instanceImageUrl))

            try:
                photo_id = yield from bot.call_shared('image_upload_single', instanceImageUrl)
            except KeyError:
                logger.warning('image plugin not loaded - using legacy code')
                photo_id = yield from bot._client.upload_image(image_data, filename=filename)

            yield from bot.coro_send_message(event.conv.id_, legacy_segments, image_id=photo_id)

        else:
            yield from bot.coro_send_message(event.conv_id, "<i>couldn't find a nice picture :( try again</i>")

    except Exception as e:
        yield from bot.coro_send_message(event.conv_id, "<i>couldn't find a suitable meme! try again</i>")
        logger.exception("FAILED TO RETRIEVE MEME")

    finally:
        _externals["running"] = False
