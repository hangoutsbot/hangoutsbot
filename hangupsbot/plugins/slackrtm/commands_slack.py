import logging
import re
import sys

from .exceptions import ( AlreadySyncingError,
                          NotSyncingError )
from .utils import _slackrtm_link_profiles


logger = logging.getLogger(__name__)


def slackCommandHandler(slackbot, msg):
    tokens = msg.text.strip().split()
    if not msg.user:
        # do not respond to messages that originate from outside slack
        return

    if len(tokens) < 2:
        return

    if tokens.pop(0).lower() in [ "@hobot", "<@" + slackbot.my_uid.lower() + ">" ]:
        command = tokens.pop(0).lower()
        args = tokens
        if command in commands_user:
            return getattr(sys.modules[__name__], command)(slackbot, msg, args)
        elif command in commands_admin:
            if msg.user in slackbot.admins:
                return getattr(sys.modules[__name__], command)(slackbot, msg, args)
            else:
                slackbot.api_call(
                    'chat.postMessage',
                    channel = msg.channel,
                    text = "@{}: {} is an admin-only command".format(msg.username, command),
                    as_user = True,
                    link_names = True )
        else:
            slackbot.api_call(
                'chat.postMessage',
                channel = msg.channel,
                text = "@{}: {} is not recognised".format(msg.username, command),
                as_user = True,
                link_names = True )

"""
command definitions

dev: due to the way the plugin reloader works, any changes to files unrelated with the
package loader (__init__.py) will require a bot restart for any changes to be reflected
"""

commands_user = [ "help",
                  "whereami",
                  "whoami",
                  "whois",
                  "admins",
                  "hangoutmembers",
                  "identify" ]

commands_admin = [ "hangouts",
                   "listsyncs",
                   "syncto",
                   "disconnect",
                   "setsyncjoinmsgs",
                   "sethotag",
                   "setimageupload",
                   "setslacktag",
                   "showslackrealnames",
                   "showhorealnames" ]

def help(slackbot, msg, args):
    """list help for all available commands"""
    lines = ["*user commands:*\n"]

    for command in commands_user:
        lines.append("* *{}*: {}\n".format(
            command,
            getattr(sys.modules[__name__], command).__doc__))

    if msg.user in slackbot.admins:
        lines.append("*admin commands:*\n")
        for command in commands_admin:
            lines.append("* *{}*: {}\n".format(
                command,
                getattr(sys.modules[__name__], command).__doc__))

    slackbot.api_call(
        'chat.postMessage',
        channel = slackbot.get_slackDM(msg.user),
        text = "\n".join(lines),
        as_user = True,
        link_names = True )

def whereami(slackbot, msg, args):
    """tells you the current channel/group id"""

    slackbot.api_call(
        'chat.postMessage',
        channel=msg.channel,
        text=u'@%s: you are in channel %s' % (msg.username, msg.channel),
        as_user=True,
        link_names=True )

def whoami(slackbot, msg, args):
    """tells you your own user id"""

    userID = slackbot.get_slackDM(msg.user)
    slackbot.api_call(
        'chat.postMessage',
        channel=userID,
        text=u'@%s: your userid is %s' % (msg.username, msg.user),
        as_user=True,
        link_names=True )

def whois(slackbot, msg, args):
    """whois @username tells you the user id of @username"""

    if not len(args):
        message = u'%s: sorry, but you have to specify a username for command `whois`' % (msg.username)
    else:
        user = args[0]
        userfmt = re.compile(r'^<@(.*)>$')
        match = userfmt.match(user)
        if match:
            user = match.group(1)
        if not user.startswith('U'):
            # username was given as string instead of mention, lookup in db
            for uid in slackbot.userinfos:
                if slackbot.userinfos[uid]['name'] == user:
                    user = uid
                    break
        if not user.startswith('U'):
            message = u'%s: sorry, but I could not find user _%s_ in this slack.' % (msg.username, user)
        else:
            message = u'@%s: the user id of _%s_ is %s' % (msg.username, slackbot.get_username(user), user)

    userID = slackbot.get_slackDM(msg.user)
    slackbot.api_call(
        'chat.postMessage',
        channel=userID,
        text=message,
        as_user=True,
        link_names=True )

def admins(slackbot, msg, args):
    """lists the slack users with admin privileges"""

    message = '@%s: my admins are:\n' % msg.username
    for a in slackbot.admins:
        message += '@%s: _%s_\n' % (slackbot.get_username(a), a)
    userID = slackbot.get_slackDM(msg.user)
    slackbot.api_call(
        'chat.postMessage',
        channel=userID,
        text=message,
        as_user=True,
        link_names=True )

def hangoutmembers(slackbot, msg, args):
    """lists the users of the hangouts synced to this channel"""

    message = '@%s: the following users are in the synced Hangout(s):\n' % msg.username
    for sync in slackbot.get_syncs(channelid=msg.channel):
        hangoutname = 'unknown'
        conv = None
        for c in slackbot.bot.list_conversations():
            if c.id_ == sync.hangoutid:
                conv = c
                hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
                break
        message += '%s aka %s (%s):\n' % (hangoutname, sync.hotag if sync.hotag else 'untagged', sync.hangoutid)
        for u in conv.users:
            message += ' + <https://plus.google.com/%s|%s>\n' % (u.id_.gaia_id, u.full_name)
    userID = slackbot.get_slackDM(msg.user)
    slackbot.api_call(
        'chat.postMessage',
        channel=userID,
        text=message,
        as_user=True,
        link_names=True )

def identify(slackbot, msg, args):
    """link your hangouts user"""

    hangoutsbot = slackbot.bot

    parameters = list(args)
    if len(parameters) < 1:
        slackbot.api_call(
            'chat.postMessage',
            channel = msg.channel,
            text = "supply hangouts user id",
            as_user = True,
            link_names = True )
        return

    remove = False
    if "remove" in parameters:
        parameters.remove("remove")
        remove = True

    _hangouts_uid = parameters.pop(0)
    hangups_user = hangoutsbot.get_hangups_user(_hangouts_uid)
    if not hangups_user.definitionsource:
        slackbot.api_call(
            'chat.postMessage',
            channel = msg.channel,
            text = "{} is not a valid hangouts user id".format(_hangouts_uid),
            as_user = True,
            link_names = True )
        return

    hangouts_uid = hangups_user.id_.chat_id
    slack_teamname = slackbot.name
    slack_uid = msg.user

    message = _slackrtm_link_profiles(hangoutsbot, hangouts_uid, slack_teamname, slack_uid, "slack", remove)

    slackbot.api_call(
        'chat.postMessage',
        channel = msg.channel,
        text = message,
        as_user = True,
        link_names = True )

def hangouts(slackbot, msg, args):
    """admin-only: lists all connected hangouts, suggested: use only in direct message"""

    message = '@%s: list of active hangouts:\n' % msg.username
    for c in slackbot.bot.list_conversations():
        message += '*%s:* _%s_\n' % (slackbot.bot.conversations.get_name(c, truncate=True), c.id_)
    userID = slackbot.get_slackDM(msg.user)
    slackbot.api_call(
        'chat.postMessage',
        channel=userID,
        text=message,
        as_user=True,
        link_names=True)

def listsyncs(slackbot, msg, args):
    """admin-only: lists all runnging sync connections, suggested: use only in direct message"""

    message = '@%s: list of current sync connections with this slack team:\n' % msg.username
    for sync in slackbot.syncs:
        hangoutname = 'unknown'
        for c in slackbot.bot.list_conversations():
            if c.id_ == sync.hangoutid:
                hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
                break
        message += '*%s (%s) : %s (%s)* _%s_\n' % (
            slackbot.get_channelgroupname(sync.channelid, 'unknown'),
            sync.channelid,
            hangoutname,
            sync.hangoutid,
            sync.getPrintableOptions()
            )
    userID = slackbot.get_slackDM(msg.user)
    slackbot.api_call(
        'chat.postMessage',
        channel=userID,
        text=message,
        as_user=True,
        link_names=True)

def syncto(slackbot, msg, args):
    """admin-only: sync messages from current channel/group to specified hangout, suggested: use only in direct message

    usage: syncto [hangout conversation id] [optional short title/tag]

    if [short title] specified, messages will be tagged with it, instead of hangout title"""

    message = '@%s: ' % msg.username
    if not len(args):
        message += u'sorry, but you have to specify a Hangout Id for command `syncto`'
        slackbot.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
        return

    hangoutid = args[0]
    shortname = None
    if len(args) > 1:
        shortname = ' '.join(args[1:])
    hangoutname = None
    for c in slackbot.bot.list_conversations():
        if c.id_ == hangoutid:
            hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
            break
    if not hangoutname:
        message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    if not shortname:
        shortname = hangoutname
    if msg.channel.startswith('D'):
        channelname = 'DM'
    else:
        channelname = '#%s' % slackbot.get_channelgroupname(msg.channel)

    try:
        slackbot.config_syncto(msg.channel, hangoutid, shortname)
    except AlreadySyncingError:
        message += u'This channel (%s) is already synced with Hangout _%s_.' % (channelname, hangoutname)
    else:
        message += u'OK, I will now sync all messages in this channel (%s) with Hangout _%s_.' % (channelname, hangoutname)
    slackbot.api_call(
        'chat.postMessage',
        channel=msg.channel,
        text=message,
        as_user=True,
        link_names=True )

def disconnect(slackbot, msg, args):
    """admin-only: stop syncing messages from current channel/group to specified hangout, suggested: use only in direct message

    usage: disconnect [hangout conversation id]"""

    message = '@%s: ' % msg.username
    if not len(args):
        message += u'sorry, but you have to specify a Hangout Id for command `disconnect`'
        slackbot.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
        return

    hangoutid = args[0]
    hangoutname = None
    for c in slackbot.bot.list_conversations():
        if c.id_ == hangoutid:
            hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
            break
    if not hangoutname:
        message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
        slackbot.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
        return

    if msg.channel.startswith('D'):
        channelname = 'DM'
    else:
        channelname = '#%s' % slackbot.get_channelgroupname(msg.channel)
    try:
        slackbot.config_disconnect(msg.channel, hangoutid)
    except NotSyncingError:
        message += u'This channel (%s) is *not* synced with Hangout _%s_.' % (channelname, hangoutid)
    else:
        message += u'OK, I will no longer sync messages in this channel (%s) with Hangout _%s_.' % (channelname, hangoutname)
    slackbot.api_call(
        'chat.postMessage',
        channel=msg.channel,
        text=message,
        as_user=True,
        link_names=True )

def setsyncjoinmsgs(slackbot, msg, args):
    """admin-only: toggle messages about membership changes in synced hangout conversation, default: enabled

    usage: setsyncjoinmsgs [hangouts conversation id] [true|false]"""

    message = '@%s: ' % msg.username
    if len(args) != 2:
        message += u'sorry, but you have to specify a Hangout Id and a `true` or `false` for command `setsyncjoinmsgs`'
        slackbot.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
        return

    hangoutid = args[0]
    enable = args[1]
    for c in slackbot.bot.list_conversations():
        if c.id_ == hangoutid:
            hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
            break
    if not hangoutname:
        message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True)
        return

    if msg.channel.startswith('D'):
        channelname = 'DM'
    else:
        channelname = '#%s' % slackbot.get_channelgroupname(msg.channel)

    if enable.lower() in ['true', 'on', 'y', 'yes']:
        enable = True
    elif enable.lower() in ['false', 'off', 'n', 'no']:
        enable = False
    else:
        message += u'sorry, but "%s" is not "true" or "false"' % enable
        slackbot.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
        return

    try:
        slackbot.config_setsyncjoinmsgs(msg.channel, hangoutid, enable)
    except NotSyncingError:
        message += u'This channel (%s) is not synced with Hangout _%s_, not changing syncjoinmsgs.' % (channelname, hangoutname)
    else:
        message += u'OK, I will %s sync join/leave messages in this channel (%s) with Hangout _%s_.' % (('now' if enable else 'no longer'), channelname, hangoutname)
    slackbot.api_call(
        'chat.postMessage',
        channel=msg.channel,
        text=message,
        as_user=True,
        link_names=True )

def sethotag(slackbot, msg, args):
    """admin-only: sets an alternate short title/tag to show on hangouts message (instead of conversation title)

    default: hangouts conversation title

    usage: sethotag [hangouts conversation id] [short title/tag|none]"""

    message = '@%s: ' % msg.username
    if len(args) < 2:
        message += u'sorry, but you have to specify a Hangout Id and a tag ("none" for no titles; "true" for chatbridge titles) for command `sethotag`'
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True)
        return

    hangoutid = args[0]
    hotag = ' '.join(args[1:])
    for c in slackbot.bot.list_conversations():
        if c.id_ == hangoutid:
            hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
            break
    if not hangoutname:
        message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    if msg.channel.startswith('D'):
        channelname = 'DM'
    else:
        channelname = '#%s' % slackbot.get_channelgroupname(msg.channel)

    if hotag == "none":
        hotag = None
        oktext = '*not* be tagged'
    elif hotag == "true":
        hotag = True
        oktext = 'be tagged with chatbridge-compatible titles'
    else:
        oktext = 'be tagged with " (%s)"' % hotag

    try:
        slackbot.config_sethotag(msg.channel, hangoutid, hotag)
    except NotSyncingError:
        message += u'This channel (%s) is not synced with Hangout _%s_, not changing Hangout tag.' % (channelname, hangoutname)
    else:
        message += u'OK, messages from Hangout _%s_ will %s in slack channel %s.' % (hangoutname, oktext, channelname)

    slackbot.api_call(
        'chat.postMessage',
        channel=msg.channel,
        text=message,
        as_user=True,
        link_names=True )

def setimageupload(slackbot, msg, args):
    """admin-only: toggle uploading of shared images to hangouts, default: enabled

    usage: setimageupload [hangouts conversation id] [true|false]"""

    message = '@%s: ' % msg.username
    if len(args) != 2:
        message += u'sorry, but you have to specify a Hangout Id and a `true` or `false` for command `setimageupload`'
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    hangoutid = args[0]
    upload = args[1]
    for c in slackbot.bot.list_conversations():
        if c.id_ == hangoutid:
            hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
            break
    if not hangoutname:
        message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    if msg.channel.startswith('D'):
        channelname = 'DM'
    else:
        channelname = '#%s' % slackbot.get_channelgroupname(msg.channel)

    if upload.lower() in ['true', 'on', 'y', 'yes']:
        upload = True
    elif upload.lower() in ['false', 'off', 'n', 'no']:
        upload = False
    else:
        message += u'sorry, but "%s" is not "true" or "false"' % upload
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    try:
        slackbot.config_setimageupload(msg.channel, hangoutid, upload)
    except NotSyncingError:
        message += u'This channel (%s) is not synced with Hangout _%s_, not changing imageupload.' % (channelname, hangoutname)
    else:
        message += u'OK, I will %s upload images shared in this channel (%s) with Hangout _%s_.' % (('now' if upload else 'no longer'), channelname, hangoutname)
    slackbot.api_call(
        'chat.postMessage',
        channel=msg.channel,
        text=message,
        as_user=True,
        link_names=True )

def setslacktag(slackbot, msg, args):
    """admin-only: sets an alternate short title/tag to show for slack messages relayed to hangouts (instead of slack team name)

    usage: setslacktag [hangouts conversation id] [short title/tag|none]"""

    message = '@%s: ' % msg.username
    if len(args) < 2:
        message += u'sorry, but you have to specify a Hangout Id and a tag ("none" for no titles; "true" for chatbridge titles) for command `setslacktag`'
        slackbot.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
        return

    hangoutid = args[0]
    slacktag = ' '.join(args[1:])
    for c in slackbot.bot.list_conversations():
        if c.id_ == hangoutid:
            hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
            break
    if not hangoutname:
        message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    if msg.channel.startswith('D'):
        channelname = 'DM'
    else:
        channelname = '#%s' % slackbot.get_channelgroupname(msg.channel)

    if slacktag == "none":
        slacktag = None
        oktext = '*not* be tagged'
    elif slacktag == "true":
        slacktag = True
        oktext = 'be tagged with chatbridge-compatible titles'
    else:
        oktext = 'be tagged with " (%s)"' % slacktag

    try:
        slackbot.config_setslacktag(msg.channel, hangoutid, slacktag)
    except NotSyncingError:
        message += u'This channel (%s) is not synced with Hangout _%s_, not changing Slack tag.' % (channelname, hangoutname)
    else:
        message += u'OK, messages in this slack channel (%s) will %s in Hangout _%s_.' % (channelname, oktext, hangoutname)
    slackbot.api_call(
        'chat.postMessage',
        channel=msg.channel,
        text=message,
        as_user=True,
        link_names=True )

def showslackrealnames(slackbot, msg, args):
    """admin-only: toggle display of real names or usernames in hangouts, default: usernames

    usage: showslackrealnames [hangouts conversation id] [true|false]"""

    message = '@%s: ' % msg.username
    if len(args) != 2:
        message += u'sorry, but you have to specify a Hangout Id and a `true` or `false` for command `showslackrealnames`'
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    hangoutid = args[0]
    realnames = args[1]
    for c in slackbot.bot.list_conversations():
        if c.id_ == hangoutid:
            hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
            break
    if not hangoutname:
        message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    if msg.channel.startswith('D'):
        channelname = 'DM'
    else:
        channelname = '#%s' % slackbot.get_channelgroupname(msg.channel)

    if realnames.lower() in ['true', 'on', 'y', 'yes']:
        realnames = True
    elif realnames.lower() in ['false', 'off', 'n', 'no']:
        realnames = False
    else:
        message += u'sorry, but "%s" is not "true" or "false"' % upload
        slackbot.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
        return

    try:
        slackbot.config_showslackrealnames(msg.channel, hangoutid, realnames)
    except NotSyncingError:
        message += u'This channel (%s) is not synced with Hangout _%s_, not changing showslackrealnames.' % (channelname, hangoutname)
    else:
        message += u'OK, I will display %s when syncing messages from this channel (%s) with Hangout _%s_.' % (('realnames' if realnames else 'usernames'), channelname, hangoutname)
    slackbot.api_call(
        'chat.postMessage',
        channel=msg.channel,
        text=message,
        as_user=True,
        link_names=True )

def showhorealnames(slackbot, msg, args):
    """admin-only: show real names and/or usernames for hangouts messages in slack, default: real

    usage: showhorealnames [hangouts conversation id] [real|nick|both]"""

    message = '@%s: ' % msg.username
    if len(args) != 2:
        message += u'sorry, but you have to specify a Hangout Id and a `real`/`nick`/`both` for command `showhorealnames`'
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    hangoutid = args[0]
    realnames = args[1]
    for c in slackbot.bot.list_conversations():
        if c.id_ == hangoutid:
            hangoutname = slackbot.bot.conversations.get_name(c, truncate=False)
            break
    if not hangoutname:
        message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
        slackbot.api_call(
            'chat.postMessage',
            channel=msg.channel,
            text=message,
            as_user=True,
            link_names=True )
        return

    if msg.channel.startswith('D'):
        channelname = 'DM'
    else:
        channelname = '#%s' % slackbot.get_channelname(msg.channel)

    if realnames not in ['real', 'nick', 'both']:
        message += u'sorry, but "%s" is not one of "real", "nick" or "both"' % upload
        slackbot.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
        return

    try:
        slackbot.config_showhorealnames(msg.channel, hangoutid, realnames)
    except NotSyncingError:
        message += u'This channel (%s) is not synced with Hangout _%s_, not changing showhorealnames.' % (channelname, hangoutname)
    else:
        message += u'OK, I will display %s names when syncing messages from this channel (%s) with Hangout _%s_.' % (realnames, channelname, hangoutname)
    slackbot.api_call(
        'chat.postMessage',
        channel=msg.channel,
        text=message,
        as_user=True,
        link_names=True )
