import logging

import hangups


logger = logging.getLogger(__name__)


def geticon(bot, event, *args):
    """ Return the avatar of the person who called this command """
    response = yield from bot._client.getentitybyid([event.user_id.chat_id])
    try:
        photo_url = "http:" + response.entities[0].properties.photo_url
    except Exception as e:
        logger.exception("{} {} {}".format(event.user_id.chat_id, e, response))

    yield from bot.coro_send_message(event.conv_id, photo_url)
