import logging

import hangups


logger = logging.getLogger(__name__)


def geticon(bot, event, *args):
    """ Return the avatar of the person who called this command """

    _response = yield from bot._client.get_entity_by_id(
        hangups.hangouts_pb2.GetEntityByIdRequest(
            request_header = bot._client.get_request_header(),
            batch_lookup_spec = [
                hangups.hangouts_pb2.EntityLookupSpec(
                    gaia_id = event.user_id.chat_id )]))

    try:
        photo_uri = _response.entity[0].properties.photo_url
    except Exception as e:
        logger.exception("{} {} {}".format(event.user_id.chat_id, e, _response))

    yield from bot.coro_send_message(event.conv_id, photo_uri)
