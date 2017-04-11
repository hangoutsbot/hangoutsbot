import logging

from .exceptions import ( AlreadySyncingError,
                          NotSyncingError )
from .utils import ( _slackrtms,
                     _slackrtm_link_profiles )


logger = logging.getLogger(__name__)


def slacks(bot, event, *args):
    """list all configured slack teams

       usage: /bot slacks"""

    lines = [ "**Configured Slack teams:**" ]

    for slackrtm in _slackrtms:
        lines.append("* {}".format(slackrtm.name))

    yield from bot.coro_send_message(event.conv_id, "\n".join(lines))

def slack_identify(bot, event, *args):
    """link your slack user

    usage: /bot slack_identify <teamname> <username>"""

    parameters = list(args)
    if len(parameters) < 2:
        yield from bot.coro_send_message(event.conv_id, "supply slack team name and user name")
        return

    remove = False
    if "remove" in parameters:
        parameters.remove("remove")
        remove = True

    slack_teamname = parameters.pop(0)
    slackrtm = False
    for _slackrtm in _slackrtms:
        if _slackrtm.name == slack_teamname:
            slackrtm = _slackrtm
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "slack team does not exist")
        return

    usersearch = " ".join(parameters).strip()
    slack_user = False
    for _slackuid, _slackuser in slackrtm.userinfos.items():
        if( _slackuser["name"] == usersearch
                or _slackuid == usersearch
                or( _slackuser["real_name"]
                        and _slackuser["real_name"].lower() == usersearch.lower() )):
            slack_user = _slackuser
            break
    if not slack_user:
        yield from bot.coro_send_message(event.conv_id, "slack user does not exist")
        return

    message = _slackrtm_link_profiles(bot, event.user_id.chat_id, slack_teamname, slack_user["id"], "hangouts", remove)

    yield from bot.coro_send_message(event.conv_id, message)

def slack_channels(bot, event, *args):
    """list all slack channels available in specified slack team

    usage: /bot slack_channels <teamname>"""

    if len(args) != 1:
        yield from bot.coro_send_message(event.conv_id, "specify slack team to get list of channels")
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    lines = ["**Channels:**"]

    slackrtm.update_channelinfos()
    for cid in slackrtm.channelinfos:
        if not slackrtm.channelinfos[cid]['is_archived']:
            lines.append("* {1} {0}".format(slackrtm.channelinfos[cid]['name'], cid))

    lines.append("**Private groups:**")

    slackrtm.update_groupinfos()
    for gid in slackrtm.groupinfos:
        if not slackrtm.groupinfos[gid]['is_archived']:
            lines.append("* {1} {0}".format(slackrtm.groupinfos[gid]['name'], gid))

    yield from bot.coro_send_message(event.conv_id, "\n".join(lines))


def slack_users(bot, event, *args):
    """list all slack channels available in specified slack team

        usage: /bot slack_users <team> <channel>"""

    if len(args) >= 3:
        honame = ' '.join(args[2:])
    else:
        if len(args) != 2:
            yield from bot.coro_send_message(event.conv_id, "specify slack team and channel")
            return
        honame = bot.conversations.get_name(event.conv)

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    slackrtm.update_channelinfos()
    channelid = args[1]
    channelname = slackrtm.get_channelgroupname(channelid)
    if not channelname:
        yield from bot.coro_send_message(
            event.conv_id,
            "there is no channel with name **{0}** in **{1}**, use _/bot slack_channels {1}_ to list all channels".format(channelid, slackname) )
        return

    lines = [ "**Slack users in channel {}**:".format(channelname) ]

    users = slackrtm.get_channel_users(channelid)
    for username, realname in sorted(users.items()):
        lines.append("* {} {}".format(username, realname))

    yield from bot.coro_send_message(event.conv_id, "\n".join(lines))


def slack_listsyncs(bot, event, *args):
    """list current conversations we are syncing

    usage: /bot slack_listsyncs"""

    lines = [ "**Currently synced:**" ]

    for slackrtm in _slackrtms:
        for sync in slackrtm.syncs:
            hangoutname = 'unknown'
            for c in bot.list_conversations():
                if c.id_ == sync.hangoutid:
                    hangoutname = bot.conversations.get_name(c, truncate=False)
                    break
            lines.append("{} : {} ({})\n  {} ({})\n  {}".format(
                slackrtm.name,
                slackrtm.get_channelgroupname(sync.channelid),
                sync.channelid,
                hangoutname,
                sync.hangoutid,
                sync.getPrintableOptions()) )

    yield from bot.coro_send_message(event.conv_id, "\n".join(lines))


def slack_syncto(bot, event, *args):
    """start syncing the current hangout to a given slack team/channel

    usage: /bot slack_syncto <teamname> <channelid>"""

    if len(args) >= 3:
        honame = ' '.join(args[2:])
    else:
        if len(args) != 2:
            yield from bot.coro_send_message(event.conv_id, "specify slack team and channel")
            return
        honame = bot.conversations.get_name(event.conv)

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    channelid = args[1]
    channelname = slackrtm.get_channelgroupname(channelid)
    if not channelname:
        yield from bot.coro_send_message(
            event.conv_id,
            "there is no channel with name **{0}** in **{1}**, use _/bot slack_channels {1}_ to list all channels".format(channelid, slackname) )
        return

    try:
        slackrtm.config_syncto(channelid, event.conv.id_, honame)
    except AlreadySyncingError:
        yield from bot.coro_send_message(event.conv_id, "hangout already synced with {} : {}".format(slackname, channelname))
        return

    yield from bot.coro_send_message(event.conv_id, "this hangout synced with {} : {}".format(slackname, channelname))


def slack_disconnect(bot, event, *args):
    """stop syncing the current hangout with given slack team and channel

    usage: /bot slack_disconnect <teamname> <channelid>"""

    if len(args) != 2:
        yield from bot.coro_send_message(event.conv_id, "specify slack team and channel")
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    channelid = args[1]
    channelname = slackrtm.get_channelgroupname(channelid)
    if not channelname:
        yield from bot.coro_send_message(
            event.conv_id,
            "there is no channel with name **{0}** in **{1}**, use _/bot slack_channels {1}_ to list all channels".format(channelid, slackname) )
        return

    try:
        slackrtm.config_disconnect(channelid, event.conv.id_)
    except NotSyncingError:
        yield from bot.coro_send_message(event.conv_id, "current hangout not previously synced with {} : {}".format(slackname, channelname))
        return

    yield from bot.coro_send_message(event.conv_id, "this hangout disconnected from {} : {}".format(slackname, channelname))


def slack_setsyncjoinmsgs(bot, event, *args):
    """enable or disable sending notifications any time someone joins/leaves/adds/invites/kicks

    usage: /bot slack_setsyncjoinmsgs <teamname> <channelid> {true|false}"""

    if len(args) != 3:
        yield from bot.coro_send_message(event.conv_id, "specify exactly three parameters: slack team, slack channel, and \"true\" or \"false\"")
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    channelid = args[1]
    channelname = slackrtm.get_channelgroupname(channelid)
    if not channelname:
        yield from bot.coro_send_message(
            event.conv_id,
            "there is no channel with name **{0}** in **{1}**, use _/bot slack_channels {1}_ to list all channels".format(channelid, slackname) )
        return

    flag = args[2]
    if flag.lower() in ['true', 'on', 'y', 'yes']:
        flag = True
    elif enable.lower() in ['false', 'off', 'n', 'no']:
        flag = False
    else:
        yield from bot.coro_send_message(event.conv_id, "cannot interpret {} as either \"true\" or \"false\"".format(flag))
        return

    try:
        slackrtm.config_setsyncjoinmsgs(channelid, event.conv.id_, flag)
    except NotSyncingError:
        yield from bot.coro_send_message(event.conv_id, "current hangout not previously synced with {} : {}".format(slackname, channelname))
        return

    if flag:
        yield from bot.coro_send_message(event.conv_id, "membership changes will be synced with {} : {}".format(slackname, channelname))
    else:
        yield from bot.coro_send_message(event.conv_id, "membership changes will no longer be synced with {} : {}".format(slackname, channelname))


def slack_setimageupload(bot, event, *args):
    """enable/disable image upload between the synced conversations (default: enabled)

    usage: /bot slack_setimageupload <teamname> <channelid> {true|false}"""

    if len(args) != 3:
        yield from bot.coro_send_message(event.conv_id, "specify exactly three parameters: slack team, slack channel, and \"true\" or \"false\"")
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    channelid = args[1]
    channelname = slackrtm.get_channelgroupname(channelid)
    if not channelname:
        yield from bot.coro_send_message(
            event.conv_id,
            "there is no channel with name **{0}** in **{1}**, use _/bot slack_channels {1}_ to list all channels".format(channelid, slackname) )
        return

    flag = args[2]
    if flag.lower() in ['true', 'on', 'y', 'yes']:
        flag = True
    elif flag.lower() in ['false', 'off', 'n', 'no']:
        flag = False
    else:
        yield from bot.coro_send_message(event.conv_id, "cannot interpret {} as either \"true\" or \"false\"".format(flag))
        return

    try:
        slackrtm.config_setimageupload(channelid, event.conv.id_, flag)
    except NotSyncingError:
        yield from bot.coro_send_message(event.conv_id, "current hangout not previously synced with {} : {}".format(slackname, channelname))
        return

    if flag:
        yield from bot.coro_send_message(event.conv_id, "images will be uploaded to this hangout when shared in {} : {}".format(slackname, channelname))
    else:
        yield from bot.coro_send_message(event.conv_id, "images will not be uploaded to this hangout when shared in {} : {}".format(slackname, channelname))


def slack_sethotag(bot, event, *args):
    """sets the identity of current hangout when syncing this conversation
    (default: title of this hangout when sync was set up, use 'none' to disable tagging)

    usage: /bot slack_hotag <teamname> <channelid> {<tag>|none}"""

    if len(args) < 3:
        yield from bot.coro_send_message(event.conv_id, "specify: slack team, slack channel, and a tag (\"none\" to disable)")
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    channelid = args[1]
    channelname = slackrtm.get_channelgroupname(channelid)
    if not channelname:
        yield from bot.coro_send_message(
            event.conv_id,
            "there is no channel with name **{0}** in **{1}**, use _/bot slack_channels {1}_ to list all channels".format(channelid, slackname) )
        return

    if len(args) == 3:
        if args[2].lower() == 'none':
            hotag = None
        elif args[2].lower() == "true":
            hotag = True
        else:
            hotag = args[2]
    else:
        hotag = ' '.join(args[2:])

    try:
        slackrtm.config_sethotag(channelid, event.conv.id_, hotag)
    except NotSyncingError:
        yield from bot.coro_send_message(event.conv_id, "current hangout not previously synced with {} : {}".format(slackname, channelname))
        return

    if hotag is True:
        yield from bot.coro_send_message(event.conv_id, "messages synced from this hangout will be tagged with chatbridge-compatible channel title".format(slackname, channelname))
    elif hotag:
        yield from bot.coro_send_message(event.conv_id, "messages synced from this hangout will be tagged \"{}\" in {} : {}".format(hotag, slackname, channelname))
    else:
        yield from bot.coro_send_message(event.conv_id, "messages synced from this hangout will not be tagged in {} : {}".format(slackname, channelname))


def slack_setslacktag(bot, event, *args):
    """sets the identity of the specified slack conversation synced to the current hangout
    (default: name of the slack team, use 'none' to disable tagging)

    usage: /bot slack_slacktag <teamname> <channelid> {<tag>|none}"""

    if len(args) < 3:
        yield from bot.coro_send_message(event.conv_id, "specify: slack team, slack channel, and a tag (\"none\" to disable)")
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    channelid = args[1]
    channelname = slackrtm.get_channelgroupname(channelid)
    if not channelname:
        yield from bot.coro_send_message(
            event.conv_id,
            "there is no channel with name **{0}** in **{1}**, use _/bot slack_channels {1}_ to list all channels".format(channelid, slackname) )
        return

    if len(args) == 3:
        if args[2].lower() == 'none':
            slacktag = None
        elif args[2].lower() == "true":
            slacktag = True
        else:
            slacktag = args[2]
    else:
        slacktag = ' '.join(args[2:])

    try:
        slackrtm.config_setslacktag(channelid, event.conv.id_, slacktag)
    except NotSyncingError:
        yield from bot.coro_send_message(event.conv_id, "current hangout not previously synced with {} : {}".format(slackname, channelname))
        return

    if slacktag is True:
        yield from bot.coro_send_message(event.conv_id, "messages from slack {} : {} will be tagged with chatbridge-compatible channel title".format(slackname, channelname))
    elif slacktag:
        yield from bot.coro_send_message(event.conv_id, "messages from slack {} : {} will be tagged with \"{}\" in this hangout".format(slackname, channelname, slacktag))
    else:
        yield from bot.coro_send_message(event.conv_id, "messages from slack {} : {} will not be tagged in this hangout".format(slackname, channelname))


def slack_showslackrealnames(bot, event, *args):
    """enable/disable display of realnames instead of usernames in messages synced from slack (default: disabled)

    usage: /bot slack_showslackrealnames <teamname> <channelid> {true|false}"""

    if len(args) != 3:
        yield from bot.coro_send_message(event.conv_id, "specify exactly three parameters: slack team, slack channel, and \"true\" or \"false\"")
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    channelid = args[1]
    channelname = slackrtm.get_channelgroupname(channelid)
    if not channelname:
        yield from bot.coro_send_message(
            event.conv_id,
            "there is no channel with name **{0}** in **{1}**, use _/bot slack_channels {1}_ to list all channels".format(channelid, slackname) )
        return

    flag = args[2]
    if flag.lower() in ['true', 'on', 'y', 'yes']:
        flag = True
    elif flag.lower() in ['false', 'off', 'n', 'no']:
        flag = False
    else:
        yield from bot.coro_send_message(event.conv_id, "cannot interpret {} as either \"true\" or \"false\"".format(flag))
        return

    try:
        slackrtm.config_showslackrealnames(channelid, event.conv.id_, flag)
    except NotSyncingError:
        yield from bot.coro_send_message(event.conv_id, "current hangout not previously synced with {} : {}".format(slackname, channelname))
        return

    if flag:
        yield from bot.coro_send_message(event.conv_id, "real names will be displayed when syncing messages from slack {} : {}".format(slackname, channelname))
    else:
        yield from bot.coro_send_message(event.conv_id, "user names will be displayed when syncing messages from slack {} : {}".format(slackname, channelname))


def slack_showhorealnames(bot, event, *args):
    """display real names and/or nicknames in messages synced from hangouts (default: real)

    usage: /bot slack_showhorealnames <teamname> <channelid> {real|nick|both}"""

    if len(args) != 3:
        yield from bot.coro_send_message(event.conv_id, "specify exactly three parameters: slack team, slack channel, and \"real\"/\"nick\"/\"both\"")
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        yield from bot.coro_send_message(event.conv_id, "there is no slack team with name **{}**, use _/bot slacks_ to list all teams".format(slackname))
        return

    channelid = args[1]
    channelname = slackrtm.get_groupname(channelid, slackrtm.get_channelname(channelid))
    if not channelname:
        yield from bot.coro_send_message(
            event.conv_id,
            "there is no channel with name **{0}** in **{1}**, use _/bot slack_channels {1}_ to list all channels".format(channelid, slackname) )
        return

    flag = args[2]
    if flag not in ['real', 'nick', 'both']:
        yield from bot.coro_send_message(event.conv_id, "cannot interpret {} as one of \"real\", \"nick\" or \"both\"".format(flag))
        return

    try:
        slackrtm.config_showhorealnames(channelid, event.conv.id_, flag)
    except NotSyncingError:
        yield from bot.coro_send_message(event.conv_id, "current hangout not previously synced with {} : {}".format(slackname, channelname))
        return

    yield from bot.coro_send_message(event.conv_id, "{} names will be displayed when syncing messages from slack {} : {}".format(flag, slackname, channelname))
