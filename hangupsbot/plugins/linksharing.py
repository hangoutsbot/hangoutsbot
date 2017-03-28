"""
Plugin for handle group links sharing
"""
import asyncio, logging, random, string

import hangups
import functools

import plugins

from commands import command


logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_admin_command(["linksharing"])
    plugins.register_shared("linksharing.get",functools.partial(_get_linksharing, bot))
    plugins.register_shared("linksharing.set",functools.partial(_set_linksharing, bot))

def _set_linksharing(bot, convid, status):

    if status:
        _status = hangups.hangouts_pb2.GROUP_LINK_SHARING_STATUS_ON
    else:
        _status = hangups.hangouts_pb2.GROUP_LINK_SHARING_STATUS_OFF

    request = hangups.hangouts_pb2.SetGroupLinkSharingEnabledRequest(
        request_header = bot._client.get_request_header(),
        event_request_header = hangups.hangouts_pb2.EventRequestHeader(
            conversation_id = hangups.hangouts_pb2.ConversationId(
                id = convid
            ),
            client_generated_id = bot._client.get_client_generated_id(),
        ),
        group_link_sharing_status=(
            _status
        ),
    )
    yield from bot._client.set_group_link_sharing_enabled(request)
    print('status set: {}'.format(
        _status
    ))
    return True

def _get_linksharing(bot, convid):

    request = hangups.hangouts_pb2.GetGroupConversationUrlRequest(
        request_header = bot._client.get_request_header(),
        conversation_id = hangups.hangouts_pb2.ConversationId(
            id = convid,
        )
    )
    response = yield from bot._client.get_group_conversation_url(request)
    url = response.group_conversation_url
    logger.info("linksharing: convid {} url: {}".format(convid, url))

    return url

def linksharing(bot, event, *args):
    """
    Set or get link sharing from conv<br />
    <b>Use:</b> /bot linksharing <get|on|off> [<convid>]
    """
    convid = event.conv_id
    command_syntax = "/bot linksharing <get|on|off> [<convid>]"
    if len(args) > 2:
        yield from bot.coro_send_message(event.conv, "<b>Use:</b> {}".format(command_syntax))
        return
    elif len(args) < 1:
        yield from bot.coro_send_message(event.conv, "<b>Use:</b> {}".format(command_syntax))
        return
    else:
        cmd = args[0]
        if cmd == "on" or cmd == "off":
            if cmd == "on":
                value = True
                verboise = "enabled linksharing"
            else:
                value = False
                verboise = "disabled linksharing"

            if len(args) == 2:
                channel = args[1]
            else:
                channel = convid

            response = yield from bot.call_shared("linksharing.set", channel, value)
            message = "{}: {}".format(verboise, response)

        elif cmd == "get":
            if len(args) == 2:
                channel = args[1]
            else:
                channel = convid

            url = yield from bot.call_shared("linksharing.get", channel)
            message = "linksharing url: {}".format(url)
        else:
            yield from bot.coro_send_message(event.conv, "<b>Use:</b> {}".format(command_syntax))
            return

    yield from bot.coro_send_message(convid, message)
