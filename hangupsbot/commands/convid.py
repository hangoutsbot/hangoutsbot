import logging, shlex

import hangups

import plugins

from utils import simple_parse_to_segments
from commands import command


logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_admin_command(["convecho", "convfilter", "convleave", "convrename", "convusers"])


def get_posix_args(rawargs):
    lexer = shlex.shlex(" ".join(rawargs), posix=True)
    lexer.commenters = ""
    lexer.wordchars += "!@#$%^&*():/.<>?[]-,=+;|"
    posix_args = list(lexer)
    return posix_args


def convfilter(bot, event, *args):
    """test filter and return matched conversations"""
    posix_args = get_posix_args(args)

    if len(posix_args) > 1:
        yield from bot.coro_send_message(event.conv_id,
            _("<em>1 parameter required, {} supplied - enclose parameter in double-quotes</em>").format(len(posix_args)))
    elif len(posix_args) <= 0:
        yield from bot.coro_send_message(event.conv_id,
            _("<em>supply 1 parameter</em>"))
    else:
        lines = []
        for convid, convdata in bot.conversations.get(filter=posix_args[0]).items():
            lines.append("`{}` <b>{}</b> ({})".format(convid, convdata["title"], len(convdata["participants"])))
        lines.append(_('<b>Total: {}</b>').format(len(lines)))
        message = '<br />'.join(lines)

        yield from bot.coro_send_message(event.conv_id, message)

        return { "api.response" : message }


def convecho(bot, event, *args):
    """echo back text into filtered conversations"""
    posix_args = get_posix_args(args)

    if(len(posix_args) > 1):
        if not posix_args[0]:
            """block spamming ALL conversations"""
            text = _("<em>sending to ALL conversations not allowed</em>")
            convlist = bot.conversations.get(filter=event.conv_id)
        else:
            convlist = bot.conversations.get(filter=posix_args[0])
            text = ' '.join(posix_args[1:])
            test_segments = simple_parse_to_segments(text)
            if test_segments:
                if test_segments[0].text.lower().strip().startswith(tuple([cmd.lower() for cmd in bot._handlers.bot_command])):
                    """detect and reject attempts to exploit botalias"""
                    text = _("<em>command echo blocked</em>")
                    convlist = bot.conversations.get(filter=event.conv_id)
    elif len(posix_args) == 1 and posix_args[0].startswith("id:"):
        """specialised error message for /bot echo (implied convid: <event.conv_id>)"""
        text = _("<em>missing text</em>")
        convlist = bot.conversations.get(filter=event.conv_id)
    else:
        """general error"""
        text = _("<em>required parameters: convfilter text</em>")
        convlist = bot.conversations.get(filter=event.conv_id)

    if not convlist:
        text = _("<em>no conversations filtered</em>")
        convlist = bot.conversations.get(filter=event.conv_id)

    for convid, convdata in convlist.items():
        yield from bot.coro_send_message(convid, text)


def convrename(bot, event, *args):
    """renames a single specified conversation"""
    posix_args = get_posix_args(args)

    if len(posix_args) > 1:
        if not posix_args[0].startswith(("id:", "text:")):
            # always force explicit search for single conversation on vague user request
            posix_args[0] = "id:" + posix_args[0]
        convlist = bot.conversations.get(filter=posix_args[0])
        title = ' '.join(posix_args[1:])

        # only act on the first matching conversation

        yield from bot._client.rename_conversation(
            hangups.hangouts_pb2.RenameConversationRequest(
                request_header = bot._client.get_request_header(),
                new_name = title,
                event_request_header = hangups.hangouts_pb2.EventRequestHeader(
                    conversation_id = hangups.hangouts_pb2.ConversationId(
                        id = list(convlist.keys())[0] ),
                    client_generated_id = bot._client.get_client_generated_id() )))

    elif len(posix_args) == 1 and posix_args[0].startswith("id:"):
        """specialised error message for /bot rename (implied convid: <event.conv_id>)"""
        text = _("<em>missing title</em>")
        convlist = bot.conversations.get(filter=event.conv_id)
        yield from command.run(bot, event, *["convecho", "id:" + event.conv_id, text])
    else:
        """general error"""
        text = _("<em>required parameters: convfilter title</em>")
        convlist = bot.conversations.get(filter=event.conv_id)
        yield from command.run(bot, event, *["convecho", "id:" + event.conv_id, text])


def convusers(bot, event, *args):
    """gets list of users for specified conversation filter"""
    posix_args = get_posix_args(args)

    if len(posix_args) != 1:
        message = _("<em>should be 1 parameter, {} supplied</em>".format(len(posix_args)))
    elif not posix_args[0]:
        """don't do it in all conversations - might crash hangups"""
        message = _("<em>retrieving ALL conversations blocked</em>")
    else:
        chunks = [] # one "chunk" = info for 1 hangout
        for convid, convdata in bot.conversations.get(filter=posix_args[0]).items():
            lines = []
            lines.append('<b>{}</b>'.format(convdata["title"], len(convdata["participants"])))
            for chat_id in convdata["participants"]:
                User = bot.get_hangups_user(chat_id)
                # name and G+ link
                _line = '<b><a href="https://plus.google.com/u/0/{}/about">{}</a></b>'.format(
                    User.id_.chat_id, User.full_name)
                # email from hangups UserList (if available)
                if User.emails:
                    _line += '<br />... (<a href="mailto:{0}">{0}</a>)'.format(User.emails[0])
                # user id
                _line += "<br />... {}".format(User.id_.chat_id) # user id
                lines.append(_line)
            lines.append(_('<b>Users: {}</b>').format(len(convdata["participants"])))
            chunks.append('<br />'.join(lines))
        message = '<br /><br />'.join(chunks)

    yield from bot.coro_send_message(event.conv_id, message)

    return { "api.response" : message }


def convleave(bot, event, *args):
    """leave specified conversation(s)"""
    posix_args = get_posix_args(args)

    if(len(posix_args) >= 1):
        if not posix_args[0]:
            """block leaving ALL conversations"""
            yield from bot.coro_send_message(event.conv_id,
                _("<em>cannot leave ALL conversations</em>"))
            return
        else:
            convlist = bot.conversations.get(filter=posix_args[0])
    else:
        """general error"""
        yield from bot.coro_send_message(event.conv_id,
            _("<em>required parameters: convfilter</em>"))
        return

    for convid, convdata in convlist.items():
        if convdata["type"] == "GROUP":
            if not "quietly" in posix_args:
                yield from bot.coro_send_message(convid, _('I\'ll be back!'))

            try:
                yield from bot._client.remove_user(
                    hangups.hangouts_pb2.RemoveUserRequest(
                        request_header = bot._client.get_request_header(),
                        event_request_header = hangups.hangouts_pb2.EventRequestHeader(
                            conversation_id = hangups.hangouts_pb2.ConversationId(
                                id = convid ),
                            client_generated_id = bot._client.get_client_generated_id() )))

                if convid in bot._conv_list._conv_dict:
                    # replicate hangups behaviour - remove conversation from internal dict
                    del bot._conv_list._conv_dict[convid]
                bot.conversations.remove(convid)

            except hangups.NetworkError as e:
                logging.exception("CONVLEAVE: error leaving {} {}".format(convid, convdata["title"]))

        else:
            logging.warning("CONVLEAVE: cannot leave {} {} {}".format(convdata["type"], convid, convdata["title"]))
