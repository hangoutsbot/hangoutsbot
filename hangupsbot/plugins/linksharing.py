"""
Plugin for handle group links sharing
"""
import logging, functools
import hangups
import plugins

logger = logging.getLogger(__name__)

def _initialise(bot):
    plugins.register_admin_command(["linksharing"])
    plugins.register_shared("linksharing.get",functools.partial(_get_linksharing, bot))
    plugins.register_shared("linksharing.set",functools.partial(_set_linksharing, bot))

def _set_linksharing(bot, convid, status):
    """shared function, sets the link to `status`, or throws an error"""
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
    return True

def _get_linksharing(bot, convid):
    """shared function, returns the url of the group link, or throws an error"""
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
    set or get link sharing from conv
    Use: /bot linksharing <get|on|off> [<convid>]
    """
    convid = event.conv_id
    command_syntax = "/bot linksharing <get|on|off> [<convid>]"
    if 1 > len(args) > 2:
        yield from bot.coro_send_message(event.conv, "<b>Use:</b> {}".format(command_syntax))
        return
    else:
        cmd = args[0]
        channel = args[1] if len(args) == 2 else convid
        if cmd == "on" or cmd == "off":
            value = cmd == "on"

            message = "linksharing enabled" if value else "linksharing disabled"
            response = yield from bot.call_shared("linksharing.set", channel, value)
        elif cmd == "get":
            url = yield from bot.call_shared("linksharing.get", channel)
            message = "linksharing url: {}".format(url)
        else:
            yield from bot.coro_send_message(event.conv, "<b>Use:</b> {}".format(command_syntax))
            return

    yield from bot.coro_send_message(convid, message)
