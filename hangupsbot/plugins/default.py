import re, json, shlex, logging

import hangups

import plugins

from utils import text_to_segments, simple_parse_to_segments, remove_accents

from commands import command


_internal = {} # non-persistent internal state independent of config.json/memory.json

_internal["broadcast"] = { "message": "", "conversations": [] } # /bot broadcast

def _initialise(bot):
    plugins.register_admin_command(["broadcast", "convecho", "convfilter", "convleave", "convrename", "convusers", "users", "user", "hangouts", "rename", "leave", "reload", "quit", "config", "whereami"])
    plugins.register_user_command(["echo", "whoami"])


def get_posix_args(rawargs):
    lexer = shlex.shlex(" ".join(rawargs), posix=True)
    lexer.commenters = ""
    lexer.wordchars += "!@#$%^&*():/.<>?[]-,=+;"
    posix_args = list(lexer)
    return posix_args


def convfilter(bot, event, *args):
    """test filter and return matched conversations"""
    posix_args = get_posix_args(args)

    if len(posix_args) > 1:
        bot.send_message_parsed(event.conv_id, 
            _("<em>1 parameter required, {} supplied - enclose parameter in double-quotes</em>").format(len(posix_args)))
    elif len(posix_args) <= 0:
        bot.send_message_parsed(event.conv_id, 
            _("<em>supply 1 parameter</em>"))
    else:
        lines = []
        for convid, convdata in bot.conversations.get(filter=posix_args[0]).items():
            lines.append("`{}` <b>{}</b> ({})".format(convid, convdata["title"], len(convdata["participants"])))
        lines.append(_('<b>Total: {}</b>').format(len(lines)))
        bot.send_message_parsed(event.conv_id, '<br />'.join(lines))


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
        bot.send_message_parsed(convid, text)


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
        yield from bot._client.setchatname(list(convlist.keys())[0], title)
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
        text = _("<em>should be 1 parameter, {} supplied</em>".format(len(posix_args)))
    elif not posix_args[0]:
        """don't do it in all conversations - might crash hangups"""
        text = _("<em>retrieving ALL conversations blocked</em>")
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
        text = '<br /><br />'.join(chunks) 

    bot.send_message_parsed(event.conv_id, text)


def convleave(bot, event, *args):
    """leave specified conversation(s)"""
    posix_args = get_posix_args(args)

    if(len(posix_args) >= 1):
        if not posix_args[0]:
            """block leaving ALL conversations"""
            bot.send_message_parsed(event.conv_id, 
                _("<em>cannot leave ALL conversations</em>"))
            return
        else:
            convlist = bot.conversations.get(filter=posix_args[0])
    else:
        """general error"""
        bot.send_message_parsed(event.conv_id, 
            _("<em>required parameters: convfilter</em>"))
        return

    for convid, convdata in convlist.items():
        if convdata["type"] == "GROUP":
            if not "quietly" in posix_args:
                bot.send_message_parsed(convid, _('I\'ll be back!'))
            yield from bot._conv_list.leave_conversation(convid)
            bot.conversations.remove(convid)
        else:
            logging.warning("CONVLEAVE: cannot leave {} {} {}".format(convdata["type"], convid, convdata["title"]))


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
            conv_info = ["<b>{}</b> ... {}".format(bot.conversations.get_name(convid), convid) for convid in _internal["broadcast"]["conversations"]]
            if not _internal["broadcast"]["message"]:
                bot.send_message_parsed(event.conv, _("broadcast: no message set"))
                return
            if not conv_info:
                bot.send_message_parsed(event.conv, _("broadcast: no conversations available"))
                return
            bot.send_message_parsed(event.conv, _(
                                            "<b>message:</b><br />"
                                            "{}<br />"
                                            "<b>to:</b><br />"
                                            "<pre>{}</pre>".format(_internal["broadcast"]["message"],
                                                "<br />".join(conv_info))))
        elif subcmd == "message":
            """set broadcast message"""
            message = ' '.join(parameters)
            if message:
                if message.lower().strip().startswith(tuple([_.lower() for _ in bot._handlers.bot_command])):
                    bot.send_message_parsed(event.conv, _("broadcast: message not allowed"))
                    return
                _internal["broadcast"]["message"] = message
            else:
                bot.send_message_parsed(event.conv, _("broadcast: message must be supplied after subcommand"))
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
            bot.send_message_parsed(event.conv, _("broadcast: {} conversation(s)".format(len(_internal["broadcast"]["conversations"]))))
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
                        removed.append("<b>{}</b> ({})".format(bot.conversations.get_name(conv), convid))
                if removed:
                    bot.send_message_parsed(event.conv, _("broadcast: removed {}".format(", ".join(removed))))
        elif subcmd == "NOW":
            """send the broadcast - no turning back!"""
            context = { "explicit_relay": True } # prevent echos across syncrooms
            for convid in _internal["broadcast"]["conversations"]:
                bot.send_message_parsed(convid, _internal["broadcast"]["message"], context=context)
            bot.send_message_parsed(event.conv, _("broadcast: message sent to {} chats".format(len(_internal["broadcast"]["conversations"]))))
        else:
            bot.send_message_parsed(event.conv, _("broadcast: /bot broadcast [info|message|add|remove|NOW] ..."))
    else:
        bot.send_message_parsed(event.conv, _("broadcast: /bot broadcast [info|message|add|remove|NOW]"))


def users(bot, event, *args):
    """list all users in current hangout (include g+ and email links)"""
    yield from command.run(bot, event, *["convusers", "id:" + event.conv_id])


def user(bot, event, username, *args):
    """find people by name"""

    username_lower = username.strip().lower()
    username_upper = username.strip().upper()

    segments = [hangups.ChatMessageSegment(_('results for user named "{}":').format(username),
                                           is_bold=True),
                hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]

    all_known_users = {}
    for chat_id in bot.memory["user_data"]:
        all_known_users[chat_id] = bot.get_hangups_user(chat_id)

    for u in sorted(all_known_users.values(), key=lambda x: x.full_name.split()[-1]):
        if (not username_lower in u.full_name.lower() and
            not username_upper in remove_accents(u.full_name.upper())):

            continue

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
    bot.send_message_segments(event.conv, segments)


def hangouts(bot, event, *args):
    """list all hangouts, supply keywords to filter by title"""

    text_search = " ".join(args)

    lines = []
    for convid, convdata in bot.conversations.get(filter="text:" + text_search).items():
        lines.append("<b>{}</b>: <em>`{}`</em>".format(convdata["title"], convid))

    lines.append(_('<b>Total: {}</b>').format(len(lines)))
    if text_search:
        lines.insert(0, _('<b>List of hangouts with keyword:</b> "<pre>{}</pre>"').format(text_search))

    bot.send_message_parsed(event.conv, "<br />".join(lines))


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
    bot.config.load()
    bot.memory.load()


def quit(bot, event, *args):
    """stop running"""
    print(_('HangupsBot killed by user {} from conversation {}').format(event.user.full_name,
                                                                     bot.conversations.get_name(event.conv)))
    yield from bot._client.disconnect()


def config(bot, event, cmd=None, *args):
    """displays or modifies the configuration
        Parameters: /bot config get [key] [subkey] [...]
                    /bot config set [key] [subkey] [...] [value]
                    /bot config append [key] [subkey] [...] [value]
                    /bot config remove [key] [subkey] [...] [value]"""

    # consume arguments and differentiate beginning of a json array or object
    tokens = list(args)
    parameters = []
    value = []
    state = "key"
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
    print("config {}".format(parameters))

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

        bot.send_message_parsed(event.conv, "<br />".join(text_parameters))
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
    bot.send_message_segments(event.conv, segments)


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

    bot.send_message_parsed(event.conv, _("<b><pre>{}</pre></b>, chat_id = <i>{}</i>").format(fullname, event.user.id_.chat_id))


def whereami(bot, event, *args):
    """get current conversation id"""

    bot.send_message_parsed(
      event.conv,
      _("You are at <b><pre>{}</pre></b>, conv_id = <i><pre>{}</pre></i>").format(
        bot.conversations.get_name(event.conv),
        event.conv.id_))
