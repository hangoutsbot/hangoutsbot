import re, json, logging

import hangups

import plugins

from utils import text_to_segments, simple_parse_to_segments, remove_accents
from commands import command


logger = logging.getLogger(__name__)


_internal = {} # non-persistent internal state independent of config.json/memory.json

_internal["broadcast"] = { "message": "", "conversations": [] } # /bot broadcast

def _initialise(bot):
    plugins.register_admin_command(["broadcast", "users", "user", "hangouts", "rename", "leave", "reload", "quit", "config", "whereami"])
    plugins.register_user_command(["echo", "whoami"])


def echo(bot, event, *args):
    """echo back text into conversation"""
    raw_arguments = event.text.split(maxsplit=3)
    if len(raw_arguments) >= 3:
        if raw_arguments[2] in bot.conversations.catalog:
            # e.g. /bot echo <convid> <text>
            # only admins can echo messages into other conversations
            admins_list = bot.get_config_suboption(event.conv_id, 'admins')
            if event.user_id.chat_id in admins_list:
                convid = raw_arguments[2]
            else:
                convid = event.conv_id
                raw_arguments = [ _("<b>only admins can echo other conversations</b>") ]
        else:
            # assumed /bot echo <text>
            convid = event.conv_id
            raw_arguments = event.text.split(maxsplit=2)

        _text = raw_arguments[-1].strip()

        if _text.startswith("raw:"):
            _text = _text[4:].strip()
        else:
            # emulate pre-2.5 bot behaviour and limitations
            _text = re.escape(_text)

        yield from command.run(bot, event, *["convecho", "id:" + convid, _text])


def broadcast(bot, event, *args):
    """broadcast a message to chats, use with care"""
    if args:
        subcmd = args[0]
        parameters = args[1:]
        if subcmd == "info":
            """display broadcast data such as message and target rooms"""

            conv_info = [ "<b><pre>{}</pre></b> ... <pre>{}</pre>".format(bot.conversations.get_name(convid), convid) 
                          for convid in _internal["broadcast"]["conversations"] ]

            if not _internal["broadcast"]["message"]:
                yield from bot.coro_send_message(event.conv, _("broadcast: no message set"))
                return

            if not conv_info:
                yield from bot.coro_send_message(event.conv, _("broadcast: no conversations available"))
                return

            yield from bot.coro_send_message(event.conv, _(
                                            "<b>message:</b><br />"
                                            "{}<br />"
                                            "<b>to:</b><br />"
                                            "{}".format(_internal["broadcast"]["message"],
                                                "<br />".join(conv_info))))

        elif subcmd == "message":
            """set broadcast message"""
            message = ' '.join(parameters)
            if message:
                if message.lower().strip().startswith(tuple([_.lower() for _ in bot._handlers.bot_command])):
                    yield from bot.coro_send_message(event.conv, _("broadcast: message not allowed"))
                    return
                _internal["broadcast"]["message"] = message

            else:
                yield from bot.coro_send_message(event.conv, _("broadcast: message must be supplied after subcommand"))

        elif subcmd == "add":
            """add conversations to a broadcast"""
            if parameters[0] == "groups":
                """add all groups (chats with users > 1, bot not counted)"""
                for convid, convdata in bot.conversations.get().items():
                    if(len(convdata["participants"]) > 1):
                        _internal["broadcast"]["conversations"].append(convid)

            elif parameters[0] == "ALL":
                """add EVERYTHING - try not to use this, will message 1-to-1s as well"""
                for convid, convdata in bot.conversations.get().items():
                    _internal["broadcast"]["conversations"].append(convid)

            else:
                """add by wild card search of title or id"""
                search = " ".join(parameters)
                for convid, convdata in bot.conversations.get().items():
                    if search.lower() in convdata["title"].lower() or search in convid:
                        _internal["broadcast"]["conversations"].append(convid)

            _internal["broadcast"]["conversations"] = list(set(_internal["broadcast"]["conversations"]))
            yield from bot.coro_send_message(event.conv, _("broadcast: {} conversation(s)".format(len(_internal["broadcast"]["conversations"]))))

        elif subcmd == "remove":
            if parameters[0].lower() == "all":
                """remove all conversations from broadcast"""
                _internal["broadcast"]["conversations"] = []

            else:
                """remove by wild card search of title or id"""
                search = " ".join(parameters)
                removed = []
                for convid in _internal["broadcast"]["conversations"]:
                    if search.lower() in bot.conversations.get_name(convid).lower() or search in convid:
                        _internal["broadcast"]["conversations"].remove(convid)
                        removed.append("<b><pre>{}</pre></b> (<pre>{}</pre>)".format(bot.conversations.get_name(convid), convid))

                if removed:
                    yield from bot.coro_send_message(event.conv, _("broadcast: removed {}".format(", ".join(removed))))

        elif subcmd == "NOW":
            """send the broadcast - no turning back!"""
            context = { "explicit_relay": True } # prevent echos across syncrooms
            for convid in _internal["broadcast"]["conversations"]:
                yield from bot.coro_send_message(convid, _internal["broadcast"]["message"], context=context)
            yield from bot.coro_send_message(event.conv, _("broadcast: message sent to {} chats".format(len(_internal["broadcast"]["conversations"]))))

        else:
            yield from bot.coro_send_message(event.conv, _("broadcast: /bot broadcast [info|message|add|remove|NOW] ..."))

    else:
        yield from bot.coro_send_message(event.conv, _("broadcast: /bot broadcast [info|message|add|remove|NOW]"))


def users(bot, event, *args):
    """list all users in current hangout (include g+ and email links)"""
    yield from command.run(bot, event, *["convusers", "id:" + event.conv_id])


def user(bot, event, *args):
    """find people by name"""

    search = " ".join(args)

    if not search:
        raise ValueError(_("supply search term"))

    search_lower = search.strip().lower()
    search_upper = search.strip().upper()

    segments = [hangups.ChatMessageSegment(_('results for user named "{}":').format(search),
                                           is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]

    all_known_users = {}
    for chat_id in bot.memory["user_data"]:
        all_known_users[chat_id] = bot.get_hangups_user(chat_id)

    for u in sorted(all_known_users.values(), key=lambda x: x.full_name.split()[-1]):
        fullname_lower = u.full_name.lower()
        fullname_upper = u.full_name.upper()
        unspaced_lower = re.sub(r'\s+', '', fullname_lower)
        unspaced_upper = re.sub(r'\s+', '', u.full_name.upper())

        if( search_lower in fullname_lower
            or search_lower in unspaced_lower
            # XXX: turkish alphabet special case: converstion works better when uppercase
            or search_upper in remove_accents(fullname_upper)
            or search_upper in remove_accents(unspaced_upper) ):

            link = 'https://plus.google.com/u/0/{}/about'.format(u.id_.chat_id)
            segments.append(hangups.ChatMessageSegment(u.full_name, hangups.SegmentType.LINK,
                                                       link_target=link))
            if u.emails:
                segments.append(hangups.ChatMessageSegment(' ('))
                segments.append(hangups.ChatMessageSegment(u.emails[0], hangups.SegmentType.LINK,
                                                           link_target='mailto:{}'.format(u.emails[0])))
                segments.append(hangups.ChatMessageSegment(')'))
            segments.append(hangups.ChatMessageSegment(' ... {}'.format(u.id_.chat_id)))
            segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))

    yield from bot.coro_send_message(event.conv, segments)


def hangouts(bot, event, *args):
    """list all hangouts, supply keywords to filter by title"""

    text_search = " ".join(args)

    lines = []
    for convid, convdata in bot.conversations.get(filter="text:" + text_search).items():
        lines.append("<b>{}</b>: <em>`{}`</em>".format(convdata["title"], convid))

    lines.append(_('<b>Total: {}</b>').format(len(lines)))
    if text_search:
        lines.insert(0, _('<b>List of hangouts with keyword:</b> "<pre>{}</pre>"').format(text_search))

    yield from bot.coro_send_message(event.conv, "<br />".join(lines))


def rename(bot, event, *args):
    """rename current hangout"""
    yield from command.run(bot, event, *["convrename", "id:" + event.conv_id, " ".join(args)])


def leave(bot, event, conversation_id=None, *args):
    """exits current or other specified hangout"""

    arglist = list(args)

    if conversation_id == "quietly":
        arglist.append("quietly")
        conversation_id = False

    if not conversation_id:
        conversation_id = event.conv_id

    yield from command.run(bot, event, *["convleave", "id:" + conversation_id, " ".join(arglist)])


def reload(bot, event, *args):
    """reload config and memory, useful if manually edited on running bot"""

    yield from bot.coro_send_message(event.conv, "<b>reloading config.json</b>")
    bot.config.load()

    yield from bot.coro_send_message(event.conv, "<b>reloading memory.json</b>")
    bot.memory.load()


def quit(bot, event, *args):
    """stop running"""
    logger.info('HangupsBot killed by user {} from conversation {}'.format(
        event.user.full_name,
        bot.conversations.get_name(event.conv)))

    yield from bot._client.disconnect()


def config(bot, event, cmd=None, *args):
    """displays or modifies the configuration

       * /bot config get [key] [subkey] [...]
       * /bot config set [key] [subkey] [...] [value]
       * /bot config append [key] [subkey] [...] [value]
       * /bot config remove [key] [subkey] [...] [value]

       note: override and display within group conversation with /bot config here [command]"""

    # consume arguments and differentiate beginning of a json array or object
    tokens = list(args)
    parameters = []
    value = []
    state = "key"

    # allow admin to override default output to 1-on-1
    chat_response_private = True
    if cmd == 'here':
        chat_response_private = False
        if tokens:
            cmd = tokens.pop(0)
        else:
            cmd = None

    for token in tokens:
        if token.startswith(("{", "[", '"', "'")):
            # apparent start of json array/object, consume into a single list item
            state = "json"
        if state == "key":
            parameters.append(token)
        elif state == "json":
            value.append(token)
        else:
            raise ValueError("unknown state")
    if value:
        parameters.append(" ".join(value))

    if cmd == 'get' or cmd is None:
        config_args = list(parameters)
        value = bot.config.get_by_path(config_args) if config_args else dict(bot.config)

    elif cmd == 'test':
        num_parameters = len(parameters)
        text_parameters = []
        last = num_parameters - 1
        for num, token in enumerate(parameters):
            if num == last:
                try:
                    json.loads(token)
                    token += " <b>(valid json)</b>"
                except ValueError:
                    token += " <em>(INVALID)</em>"
            text_parameters.append(str(num + 1) + ": " + token)
        text_parameters.insert(0, "<b>config test</b>")

        if num_parameters == 1:
            text_parameters.append(_("<em>note: testing single parameter as json</em>"))
        elif num_parameters < 1:
            yield from command.unknown_command(bot, event)
            return

        yield from bot.coro_send_message(event.conv, "<br />".join(text_parameters))
        return

    elif cmd == 'set':
        config_args = list(parameters[:-1])
        if len(parameters) >= 2:
            bot.config.set_by_path(config_args, json.loads(parameters[-1]))
            bot.config.save()
            value = bot.config.get_by_path(config_args)
        else:
            yield from command.unknown_command(bot, event)
            return

    elif cmd == 'append':
        config_args = list(parameters[:-1])
        if len(parameters) >= 2:
            value = bot.config.get_by_path(config_args)
            if isinstance(value, list):
                value.append(json.loads(parameters[-1]))
                bot.config.set_by_path(config_args, value)
                bot.config.save()
            else:
                value = _('append failed on non-list')
        else:
            yield from command.unknown_command(bot, event)
            return

    elif cmd == 'remove':
        config_args = list(parameters[:-1])
        if len(parameters) >= 2:
            value = bot.config.get_by_path(config_args)
            if isinstance(value, list):
                value.remove(json.loads(parameters[-1]))
                bot.config.set_by_path(config_args, value)
                bot.config.save()
            else:
                value = _('remove failed on non-list')
        else:
            yield from command.unknown_command(bot, event)
            return

    else:
        yield from command.unknown_command(bot, event)
        return

    if value is None:
        value = _('Parameter does not exist!')

    config_path = ' '.join(k for k in ['config'] + config_args)
    segments = [hangups.ChatMessageSegment('{}:'.format(config_path),
                                           is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
    segments.extend(text_to_segments(json.dumps(value, indent=2, sort_keys=True)))
    if chat_response_private:
        yield from bot.coro_send_to_user(event.user.id_.chat_id, segments)
    else:
        yield from bot.coro_send_message(event.conv, segments)


def whoami(bot, event, *args):
    """get your user id"""

    if bot.memory.exists(['user_data', event.user_id.chat_id, "nickname"]):
        try:
            fullname = '{0} ({1})'.format(event.user.full_name.split(' ', 1)[0]
                , bot.get_memory_suboption(event.user_id.chat_id, 'nickname'))
        except TypeError:
            fullname = event.user.full_name
    else:
        fullname = event.user.full_name

    yield from bot.coro_send_message(event.conv, _("<b><pre>{}</pre></b>, chat_id = <i>{}</i>").format(fullname, event.user.id_.chat_id))


def whereami(bot, event, *args):
    """get current conversation id"""

    yield from bot.coro_send_message(
      event.conv,
      _("You are at <b><pre>{}</pre></b>, conv_id = <i><pre>{}</pre></i>").format(
        bot.conversations.get_name(event.conv),
        event.conv.id_))
