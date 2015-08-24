import asyncio, inspect, logging, sys

# hangups-specific imports

import json, random

from hangups import exceptions
from hangups.client import Client as class_hangups_client
from hangups.schemas import OffTheRecordStatus


logger = logging.getLogger(__name__)


def _initialise(bot):
    replace_method(class_hangups_client, "removeuser", otr_monkeypatch_removeuser)
    replace_method(class_hangups_client, "adduser", otr_monkeypatched_adduser)

    # store a reference to the bot object
    this_module = sys.modules[__name__]
    setattr(this_module, "bot", bot)


def replace_method(the_class, class_method_name, new_method):
    class_method = getattr(the_class, class_method_name)

    old_signature = set(inspect.signature(class_method).parameters)
    new_signature = set(inspect.signature(new_method).parameters)

    if old_signature < new_signature: # only patch if SUBSET of parameters
        setattr(the_class, class_method_name, new_method)
        logger.info("{} replaced with {}".format(class_method_name, new_method.__name__))


@asyncio.coroutine
def otr_monkeypatch_removeuser(self, conversation_id, otr_status=None):
    if otr_status is None:
        otr_status = OffTheRecordStatus.ON_THE_RECORD # default
        try:
            if not bot.conversations.catalog[conversation_id]["history"]:
                otr_status = OffTheRecordStatus.OFF_THE_RECORD
        except KeyError:
            logger.warning("missing history flag: {}".format(conversation_id))
    logger.debug("hangups.client.Client.removeuser, convid={} OTR={}".format(conversation_id, otr_status))

    # https://github.com/tdryer/hangups/blob/5ca47c7497c1456e99cef0f8d3dc5fc8c3ffe9df/hangups/client.py#L510

    """Leave group conversation.
    conversation_id must be a valid conversation ID.
    Raises hangups.NetworkError if the request fails.
    """
    client_generated_id = random.randint(0, 2**32)
    res = yield from self._request('conversations/removeuser', [
        self._get_request_header(),
        None, None, None,
        [
            [conversation_id], client_generated_id, otr_status.value
        ],
    ])
    res = json.loads(res.body.decode())
    res_status = res['response_header']['status']
    if res_status != 'OK':
        raise exceptions.NetworkError('Unexpected status: {}'
                                      .format(res_status))


@asyncio.coroutine
def otr_monkeypatched_adduser(self, conversation_id, chat_id_list, otr_status=None):
    if otr_status is None:
        otr_status = OffTheRecordStatus.ON_THE_RECORD # default
        try:
            if not bot.conversations.catalog[conversation_id]["history"]:
                otr_status = OffTheRecordStatus.OFF_THE_RECORD
        except KeyError:
            logger.warning("missing history flag: {}".format(conversation_id))
    logger.debug("hangups.client.Client.adduser, convid={} OTR={}".format(conversation_id, otr_status))

    # https://github.com/tdryer/hangups/blob/5ca47c7497c1456e99cef0f8d3dc5fc8c3ffe9df/hangups/client.py#L858

    """Add user to existing conversation.
    conversation_id must be a valid conversation ID.
    chat_id_list is list of users which should be invited to conversation.
    Raises hangups.NetworkError if the request fails.
    """
    client_generated_id = random.randint(0, 2**32)
    body = [
        self._get_request_header(),
        None,
        [[str(chat_id), None, None, "unknown", None, []]
         for chat_id in chat_id_list],
        None,
        [
            [conversation_id], client_generated_id, otr_status.value, None, 4
        ]
    ]

    res = yield from self._request('conversations/adduser', body)
    # can return 200 but still contain an error
    res = json.loads(res.body.decode())
    res_status = res['response_header']['status']
    if res_status != 'OK':
        raise exceptions.NetworkError('Unexpected status: {}'
                                      .format(res_status))
    return res