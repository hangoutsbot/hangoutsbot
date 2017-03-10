"""
Improved Slack sync plugin using the Slack RTM API instead of webhooks.
(c) 2015 Patrick Cernko <errror@gmx.de>


Create a Slack bot integration (not webhooks!) for each team you want
to sync into hangouts.

Your config.json should have a slackrtm section that looks something
like this.  You only need one entry per Slack team, not per channel,
unlike the legacy code.

    "slackrtm": [
        {
            "name": "SlackTeamNameForLoggingCommandsEtc",
            "key": "SLACK_TEAM1_BOT_API_KEY",
            "admins": [ "U01", "U02" ]
        },
        {
            "name": "OptionalSlackOtherTeamNameForLoggingCommandsEtc",
            "key": "SLACK_TEAM2_BOT_API_KEY",
            "admins": [ "U01", "U02" ]
        }
    ]

name = slack team name
key = slack bot api key for that team (xoxb-xxxxxxx...)
admins = user_id from slack (you can use https://api.slack.com/methods/auth.test/test to find it)

You can set up as many slack teams per bot as you like by extending the list.

Once the team(s) are configured, and the hangupsbot is restarted, invite
the newly created Slack bot into any channel or group that you want to sync,
and then use the command:
    @botname syncto <hangoutsid>

Use "@botname help" for more help on the Slack side and /bot help <command> on
the Hangouts side for more help.

"""

import asyncio
import json
import logging
import os
import pprint
import re
import threading
import time
import urllib.request
import mimetypes

import hangups

import plugins

import emoji
from websocket import WebSocketConnectionClosedException
from slackclient import SlackClient
import html # for html.unescape

logger = logging.getLogger(__name__)

# fix for simple_smile support
emoji.EMOJI_UNICODE[':simple_smile:'] = emoji.EMOJI_UNICODE[':white_smiling_face:']
emoji.EMOJI_ALIAS_UNICODE[':simple_smile:'] = emoji.EMOJI_UNICODE[':white_smiling_face:']

def chatMessageEvent2SlackText(event):
    def renderTextSegment(segment):
        out = ''
        if segment.is_bold:
            out += ' *'
        if segment.is_italic:
            out += ' _'
        out += segment.text
        if segment.is_italic:
            out += '_ '
        if segment.is_bold:
            out += '* '
        return out

    lines = ['']
    for segment in event.segments:
        if segment.type_ == hangups.schemas.SegmentType.TEXT:
            lines[-1] += renderTextSegment(segment)
        elif segment.type_ == hangups.schemas.SegmentType.LINK:
            lines[-1] += segment.text
        elif segment.type_ == hangups.schemas.SegmentType.LINE_BREAK:
            lines.append('')
        else:
            logger.warning('Ignoring unknown chat message segment type: %s', segment.type_)
    lines.extend(event.attachments)
    return '\n'.join(lines)


class ParseError(Exception):
    pass


class AlreadySyncingError(Exception):
    pass


class NotSyncingError(Exception):
    pass


class ConnectionFailedError(Exception):
    pass


class IncompleteLoginError(Exception):
    pass


class SlackMessage(object):
    def __init__(self, slackrtm, reply):
        self.text = None
        self.user = None
        self.username = None
        self.username4ho = None
        self.realname4ho = None
        self.tag_from_slack = None
        self.edited = None
        self.from_ho_id = None
        self.sender_id = None
        self.channel = None
        self.file_attachment = None

        if 'type' not in reply:
            raise ParseError('no "type" in reply: %s' % str(reply))

        if reply['type'] in ['pong', 'presence_change', 'user_typing', 'file_shared', 'file_public', 'file_comment_added', 'file_comment_deleted', 'message_deleted']:
            # we ignore pong's as they are only answers for our pings
            raise ParseError('not a "message" type reply: type=%s' % reply['type'])

        text = u''
        username = ''
        edited = ''
        from_ho_id = ''
        sender_id = ''
        channel = None
        is_joinleave = False
        # only used during parsing
        user = ''
        is_bot = False
        if reply['type'] == 'message' and 'subtype' in reply and reply['subtype'] == 'message_changed':
            if 'edited' in reply['message']:
                edited = '(Edited)'
                user = reply['message']['edited']['user']
                text = reply['message']['text']
            else:
                # sent images from HO got an additional message_changed subtype without an 'edited' when slack renders the preview
                if 'username' in reply['message']:
                    # we ignore them as we already got the (unedited) message
                    raise ParseError('ignore "edited" message from bot, possibly slack-added preview')
                else:
                    raise ParseError('strange edited message without "edited" member:\n%s' % str(reply))
        elif reply['type'] == 'message' and 'subtype' in reply and reply['subtype'] == 'file_comment':
            user = reply['comment']['user']
            text = reply['text']
        elif reply['type'] == 'file_comment_added':
            user = reply['comment']['user']
            text = reply['comment']['comment']
        else:
            if reply['type'] == 'message' and 'subtype' in reply and reply['subtype'] == 'bot_message' and 'user' not in reply:
                is_bot = True
                # this might be a HO relayed message, check if username is set and use it as username
                username = reply['username']
            elif 'text' not in reply or 'user' not in reply:
                raise ParseError('no text/user in reply:\n%s' % str(reply))
            else:
                user = reply['user']
            if 'text' not in reply or not len(reply['text']):
                # IFTTT?
                if 'attachments' in reply:
                    if 'text' in reply['attachments'][0]:
                        text = reply['attachments'][0]['text']
                    else:
                        raise ParseError('strange message without text in attachments:\n%s' % pprint.pformat(reply))
                    if 'fields' in reply['attachments'][0]:
                        for field in reply['attachments'][0]['fields']:
                            text += "\n*%s*\n%s" % (field['title'], field['value'])
                else:
                    raise ParseError('strange message without text and without attachments:\n%s' % pprint.pformat(reply))
            else:
                text = reply['text']
        file_attachment = None
        if 'file' in reply:
            if 'url_private_download' in reply['file']:
                file_attachment = reply['file']['url_private_download']

        # now we check if the message has the hidden ho relay tag, extract and remove it
        hoidfmt = re.compile(r'^(.*) <ho://([^/]+)/([^|]+)\| >$', re.MULTILINE | re.DOTALL)
        match = hoidfmt.match(text)
        if match:
            text = match.group(1)
            from_ho_id = match.group(2)
            sender_id = match.group(3)
            if 'googleusercontent.com' in text:
                gucfmt = re.compile(r'^(.*)<(https?://[^\s/]*googleusercontent.com/[^\s]*)>$', re.MULTILINE | re.DOTALL)
                match = gucfmt.match(text)
                if match:
                    text = match.group(1)
                    file_attachment = match.group(2)

        # text now contains the real message, but html entities have to be dequoted still
        text = html.unescape(text)

        username4ho = username
        realname4ho = username
        if not is_bot:
            domain = slackrtm.get_slack_domain()
            username = slackrtm.get_username(user, user)
            realname = slackrtm.get_realname(user,username)

            username4ho = u'<a href="https://%s.slack.com/team/%s">%s</a>' % (domain, username, username)
            realname4ho = u'<a href="https://%s.slack.com/team/%s">%s</a>' % (domain, username, realname)
            tag_from_slack = True
        elif sender_id != '':
            username4ho = u'<a href="https://plus.google.com/%s">%s</a>' % (sender_id, username)
            realname4ho = u'<a href="https://plus.google.com/%s">%s</a>' % (sender_id, username)
            tag_from_slack = False

        if 'channel' in reply:
            channel = reply['channel']
        elif 'group' in reply:
            channel = reply['group']
        if not channel:
            raise ParseError('no channel found in reply:\n%s' % pprint.pformat(reply))

        if reply['type'] == 'message' and 'subtype' in reply and reply['subtype'] in ['channel_join', 'channel_leave', 'group_join', 'group_leave']:
            is_joinleave = True

        self.text = text
        self.user = user
        self.username = username
        self.username4ho = username4ho
        self.realname4ho = realname4ho
        self.tag_from_slack = tag_from_slack
        self.edited = edited
        self.from_ho_id = from_ho_id
        self.sender_id = sender_id
        self.channel = channel
        self.file_attachment = file_attachment
        self.is_joinleave = is_joinleave


class SlackRTMSync(object):
    def __init__(self, channelid, hangoutid, hotag, slacktag, sync_joins=True, image_upload=True, showslackrealnames=False):
        self.channelid = channelid
        self.hangoutid = hangoutid
        self.hotag = hotag
        self.sync_joins = sync_joins
        self.image_upload = image_upload
        self.slacktag = slacktag
        self.showslackrealnames = showslackrealnames

    @staticmethod
    def fromDict(sync_dict):
        sync_joins = True
        if 'sync_joins' in sync_dict and not sync_dict['sync_joins']:
            sync_joins = False
        image_upload = True
        if 'image_upload' in sync_dict and not sync_dict['image_upload']:
            image_upload = False
        slacktag = None
        if 'slacktag' in sync_dict:
            slacktag = sync_dict['slacktag']
        else:
            slacktag = 'NOT_IN_CONFIG'
        realnames = True
        if 'showslackrealnames' in sync_dict and not sync_dict['showslackrealnames']:
            realnames = False
        return SlackRTMSync(sync_dict['channelid'], sync_dict['hangoutid'], sync_dict['hotag'], slacktag, sync_joins, image_upload, realnames)

    def toDict(self):
        return {
            'channelid': self.channelid,
            'hangoutid': self.hangoutid,
            'hotag': self.hotag,
            'sync_joins': self.sync_joins,
            'image_upload': self.image_upload,
            'slacktag': self.slacktag,
            'showslackrealnames': self.showslackrealnames,
            }

    def getPrintableOptions(self):
        return 'hotag="%s", sync_joins=%s, image_upload=%s, slacktag=%s, showslackrealnames=%s' % (
            self.hotag if self.hotag else 'NONE',
            self.sync_joins,
            self.image_upload,
            self.slacktag if self.slacktag else 'NONE',
            self.showslackrealnames,
            )


class SlackRTM(object):
    def __init__(self, sink_config, bot, loop, threaded=False):
        self.bot = bot
        self.loop = loop
        self.config = sink_config
        self.apikey = self.config['key']
        self.threadname = None
        self.lastimg = ''

        self.slack = SlackClient(self.apikey)
        if not self.slack.rtm_connect():
            raise ConnectionFailedError
        for key in ['self', 'team', 'users', 'channels', 'groups']:
            if key not in self.slack.server.login_data:
                raise IncompleteLoginError
        if threaded:
            if 'name' in self.config:
                self.name = self.config['name']
            else:
                self.name = '%s@%s' % (self.slack.server.login_data['self']['name'], self.slack.server.login_data['team']['domain'])
                logger.warning('no name set in config file, using computed name %s', self.name)
            self.threadname = 'SlackRTM:' + self.name
            threading.current_thread().name = self.threadname
            logger.info('started RTM connection for SlackRTM thread %s', pprint.pformat(threading.current_thread()))
            for t in threading.enumerate():
                if t.name == self.threadname and t != threading.current_thread():
                    logger.info('old thread found: %s - killing it', pprint.pformat(t))
                    t.stop()

        self.update_userinfos(self.slack.server.login_data['users'])
        self.update_channelinfos(self.slack.server.login_data['channels'])
        self.update_groupinfos(self.slack.server.login_data['groups'])
        self.update_teaminfos(self.slack.server.login_data['team'])
        self.dminfos = {}
        self.my_uid = self.slack.server.login_data['self']['id']

        self.admins = []
        if 'admins' in self.config:
            for a in self.config['admins']:
                if a not in self.userinfos:
                    logger.warning('userid %s not found in user list, ignoring', a)
                else:
                    self.admins.append(a)
        if not len(self.admins):
            logger.warning('no admins specified in config file')

        self.hangoutids = {}
        self.hangoutnames = {}
        for c in self.bot.list_conversations():
            name = self.bot.conversations.get_name(c, truncate=True)
            self.hangoutids[name] = c.id_
            self.hangoutnames[c.id_] = name

        self.syncs = []
        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            sync = SlackRTMSync.fromDict(s)
            if sync.slacktag == 'NOT_IN_CONFIG':
                sync.slacktag = self.get_teamname()
            self.syncs.append(sync)
        if 'synced_conversations' in self.config and len(self.config['synced_conversations']):
            logger.warning('defining synced_conversations in config is deprecated')
            for conv in self.config['synced_conversations']:
                if len(conv) == 3:
                    hotag = conv[2]
                else:
                    if conv[1] not in self.hangoutnames:
                        logger.error("could not find conv %s in bot's conversations, but used in (deprecated) synced_conversations in config!", conv[1])
                        hotag = conv[1]
                    else:
                        hotag = self.hangoutnames[conv[1]]
                self.syncs.append(SlackRTMSync(conv[0], conv[1], hotag, self.get_teamname()))

    # As of https://github.com/slackhq/python-slackclient/commit/ac343caf6a3fd8f4b16a79246264a05a7d257760
    # SlackClient.api_call returns a pre-parsed json object (a dict).
    # Wrap this call in a compatibility duck-hunt.
    def api_call(self, *args, **kwargs):
        response = self.slack.api_call(*args, **kwargs)
        if isinstance(response, str):
            try:
                response = response.decode('utf-8')
            except:
                pass
            response = json.loads(response)

        return response

    def get_slackDM(self, userid):
        if not userid in self.dminfos:
            self.dminfos[userid] = self.api_call('im.open', user = userid)['channel']
        return self.dminfos[userid]['id']

    def update_userinfos(self, users=None):
        if users is None:
            response = self.api_call('users.list')
            users = response['members']
        userinfos = {}
        for u in users:
            userinfos[u['id']] = u
        self.userinfos = userinfos

    def get_channel_users(self, channelid, default=None):
        channelinfo = None
        if channelid.startswith('C'):
            if not channelid in self.channelinfos:
                self.update_channelinfos()
            if not channelid in self.channelinfos:
                logger.error('get_channel_users: Failed to find channel %s' % channelid)
                return None
            else:
                channelinfo = self.channelinfos[channelid]
        else:
            if not channelid in self.groupinfos:
                self.update_groupinfos()
            if not channelid in self.groupinfos:
                logger.error('get_channel_users: Failed to find private group %s' % channelid)
                return None
            else:
                channelinfo = self.groupinfos[channelid]

        channelusers = channelinfo['members']
        users = {}
        for u in channelusers:
            username = self.get_username(u)
            realname = self.get_realname(u, "No real name")
            if username:
                users[username+" "+u] = realname

        return users

    def update_teaminfos(self, team=None):
        if team is None:
            response = self.api_call('team.info')
            team = response['team']
        self.team = team

    def get_teamname(self):
        # team info is static, no need to update
        return self.team['name']

    def get_slack_domain(self):
        # team info is static, no need to update
        return self.team['domain']

    def get_realname(self, user, default=None):
        if user not in self.userinfos:
            logger.debug('user not found, reloading users')
            self.update_userinfos()
            if user not in self.userinfos:
                logger.warning('could not find user "%s" although reloaded', user)
                return default
        if not self.userinfos[user]['real_name']:
            return default
        return self.userinfos[user]['real_name']


    def get_username(self, user, default=None):
        if user not in self.userinfos:
            logger.debug('user not found, reloading users')
            self.update_userinfos()
            if user not in self.userinfos:
                logger.warning('could not find user "%s" although reloaded', user)
                return default
        return self.userinfos[user]['name']

    def update_channelinfos(self, channels=None):
        if channels is None:
            response = self.api_call('channels.list')
            channels = response['channels']
        channelinfos = {}
        for c in channels:
            channelinfos[c['id']] = c
        self.channelinfos = channelinfos

    def get_channelname(self, channel, default=None):
        if channel not in self.channelinfos:
            logger.debug('channel not found, reloading channels')
            self.update_channelinfos()
            if channel not in self.channelinfos:
                logger.warning('could not find channel "%s" although reloaded', channel)
                return default
        return self.channelinfos[channel]['name']

    def update_groupinfos(self, groups=None):
        if groups is None:
            response = self.api_call('groups.list')
            groups = response['groups']
        groupinfos = {}
        for c in groups:
            groupinfos[c['id']] = c
        self.groupinfos = groupinfos

    def get_groupname(self, group, default=None):
        if group not in self.groupinfos:
            logger.debug('group not found, reloading groups')
            self.update_groupinfos()
            if group not in self.groupinfos:
                logger.warning('could not find group "%s" although reloaded', group)
                return default
        return self.groupinfos[group]['name']

    def get_syncs(self, channelid=None, hangoutid=None):
        syncs = []
        for sync in self.syncs:
            if channelid == sync.channelid:
                syncs.append(sync)
            elif hangoutid == sync.hangoutid:
                syncs.append(sync)
        return syncs

    def rtm_read(self):
        return self.slack.rtm_read()

    def ping(self):
        return self.slack.server.ping()

    def matchReference(self, match):
        out = ""
        linktext = ""
        if match.group(5) == '|':
            linktext = match.group(6)
        if match.group(2) == '@':
            if linktext != "":
                out = linktext
            else:
                out = "@%s" % self.get_username(match.group(3), 'unknown:%s' % match.group(3))
        elif match.group(2) == '#':
            if linktext != "":
                out = "#%s" % linktext
            else:
                out = "#%s" % self.get_channelname(match.group(3), 'unknown:%s' % match.group(3))
        else:
            linktarget = match.group(1)
            if linktext == "":
                linktext = linktarget
            out = '<a href="%s">%s</a>' % (linktarget, linktext)
        out = out.replace('_', '%5F')
        out = out.replace('*', '%2A')
        out = out.replace('`', '%60')
        return out

    def textToHtml(self, text):
        reffmt = re.compile(r'<((.)([^|>]*))((\|)([^>]*)|([^>]*))>')
        text = reffmt.sub(self.matchReference, text)
        text = emoji.emojize(text, use_aliases=True)
        text = ' %s ' % text
        bfmt = re.compile(r'([\s*_`])\*([^*]*)\*([\s*_`])')
        text = bfmt.sub(r'\1<b>\2</b>\3', text)
        ifmt = re.compile(r'([\s*_`])_([^_]*)_([\s*_`])')
        text = ifmt.sub(r'\1<i>\2</i>\3', text)
        pfmt = re.compile(r'([\s*_`])```([^`]*)```([\s*_`])')
        text = pfmt.sub(r'\1"\2"\3', text)
        cfmt = re.compile(r'([\s*_`])`([^`]*)`([\s*_`])')
        text = cfmt.sub(r"\1'\2'\3", text)
        text = text.replace("\r\n", "\n")
        text = text.replace("\n", " <br/>")
        if text[0] == ' ' and text[-1] == ' ':
            text = text[1:-1]
        else:
            logger.warning('leading or trailing space missing: "%s"', text)
        return text

    @asyncio.coroutine
    def upload_image(self, hoid, image):
        try:
            token = self.apikey
            logger.info('downloading %s', image)
            filename = os.path.basename(image)
            request = urllib.request.Request(image)
            request.add_header("Authorization", "Bearer %s" % token)
            image_response = urllib.request.urlopen(request)
            content_type = image_response.info().get_content_type()
            filename_extension = mimetypes.guess_extension(content_type)
            if filename[-(len(filename_extension)):] != filename_extension:
                logger.info('No correct file extension found, appending "%s"' % filename_extension)
                filename += filename_extension
            logger.info('uploading as %s', filename)
            image_id = yield from self.bot._client.upload_image(image_response, filename=filename)
            logger.info('sending HO message, image_id: %s', image_id)
            self.bot.send_message_segments(hoid, None, image_id=image_id)
        except Exception as e:
            logger.exception('upload_image: %s(%s)', type(e), str(e))

    def handleCommands(self, msg):
        cmdfmt = re.compile(r'^<@'+self.my_uid+r'>:?\s+(help|whereami|whoami|whois|admins|hangoutmembers|hangouts|listsyncs|syncto|disconnect|setsyncjoinmsgs|sethotag|setimageupload|setslacktag|showslackrealnames)', re.IGNORECASE)
        match = cmdfmt.match(msg.text)
        if not match:
            return
        command = match.group(1).lower()
        args = msg.text.split()[2:]

        if command == 'help':
            message = u'@%s: I understand the following commands:\n' % msg.username
            message += u'<@%s> whereami _tells you the current channel/group id_\n' % self.my_uid
            message += u'<@%s> whoami _tells you your own user id_\n' % self.my_uid
            message += u'<@%s> whois @username _tells you the user id of @username_\n' % self.my_uid
            message += u'<@%s> admins _lists the slack users with admin priveledges_\n' % self.my_uid
            message += u'<@%s> hangoutmembers _lists the users of the hangouts synced to this channel_\n' % self.my_uid
            message += u'<@%s> hangouts _lists all connected hangouts (only available for admins, use in DM with me suggested)_\n' % self.my_uid
            message += u'<@%s> listsyncs _lists all runnging sync connections (only available for admins, use in DM with me suggested)_\n' % self.my_uid
            message += u'<@%s> syncto HangoutId [shortname] _starts syncing messages from current channel/group to specified Hangout, if shortname given, messages from the Hangout will be tagged with shortname instead of Hangout title (only available for admins)_\n' % self.my_uid
            message += u'<@%s> disconnect HangoutId _stops syncing messages from current channel/group to specified Hangout (only available for admins)_\n' % self.my_uid
            message += u'<@%s> setsyncjoinmsgs HangoutId [true|false] _enable/disable messages about joins/leaves/adds/invites/kicks in synced Hangout/channel, default is enabled (only available for admins)_\n' % self.my_uid
            message += u'<@%s> sethotag HangoutId [HOTAG|none] _set the tag, that is displayed in Slack for messages from that Hangout (behind the user\'s name), default is the hangout title when sync was set up, use "none" if you want to disable tag display  (only available for admins)_\n' % self.my_uid
            message += u'<@%s> setimageupload HangoutId [true|false] _enable/disable upload of shared images in synced Hangout, default is enabled (only available for admins)_\n' % self.my_uid
            message += u'<@%s> setslacktag HangoutId [SLACKTAG|none] _set the tag, that is displayed in that Hangout for messages from the current Slack channel (behind the user\'s name), default is the Slack team name, use "none" if you want to disable tag display (only available for admins)_\n' % self.my_uid
            message += u'<@%s> showslackrealnames HangoutId [true|false] _enable/disable display of realname instead of username in handouts when syncing slack messages, default is disabled (only available for admins)_\n' % self.my_uid
            userID = self.get_slackDM(msg.user)
            self.api_call('chat.postMessage',
                          channel=userID,
                          text=message,
                          as_user=True,
                          link_names=True)

        elif command == 'whereami':
            self.api_call('chat.postMessage',
                          channel=msg.channel,
                          text=u'@%s: you are in channel %s' % (msg.username, msg.channel),
                          as_user=True,
                          link_names=True)

        elif command == 'whoami':
            userID = self.get_slackDM(msg.user)
            self.api_call('chat.postMessage',
                          channel=userID,
                          text=u'@%s: your userid is %s' % (msg.username, msg.user),
                          as_user=True,
                          link_names=True)

        elif command == 'whois':
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
                    for uid in self.userinfos:
                        if self.userinfos[uid]['name'] == user:
                            user = uid
                            break
                if not user.startswith('U'):
                    message = u'%s: sorry, but I could not find user _%s_ in this slack.' % (msg.username, user)
                else:
                    message = u'@%s: the user id of _%s_ is %s' % (msg.username, self.get_username(user), user)
            userID = self.get_slackDM(msg.user)
            self.api_call('chat.postMessage',
                          channel=userID,
                          text=message,
                          as_user=True,
                          link_names=True)

        elif command == 'admins':
            message = '@%s: my admins are:\n' % msg.username
            for a in self.admins:
                message += '@%s: _%s_\n' % (self.get_username(a), a)
            userID = self.get_slackDM(msg.user)
            self.api_call('chat.postMessage',
                          channel=userID,
                          text=message,
                          as_user=True,
                          link_names=True)

        elif command == 'hangoutmembers':
            message = '@%s: the following users are in the synced Hangout(s):\n' % msg.username
            for sync in self.get_syncs(channelid=msg.channel):
                hangoutname = 'unknown'
                conv = None
                for c in self.bot.list_conversations():
                    if c.id_ == sync.hangoutid:
                        conv = c
                        hangoutname = self.bot.conversations.get_name(c, truncate=False)
                        break
                message += '%s aka %s (%s):\n' % (hangoutname, sync.hotag if sync.hotag else 'untagged', sync.hangoutid)
                for u in conv.users:
                    message += ' + <https://plus.google.com/%s|%s>\n' % (u.id_.gaia_id, u.full_name)
            userID = self.get_slackDM(msg.user)
            self.api_call('chat.postMessage',
                  channel=userID,
                  text=message,
                  as_user=True,
                  link_names=True)

        else:
            # the remaining commands are for admins only
            if msg.user not in self.admins:
                self.api_call('chat.postMessage',
                              channel=msg.channel,
                              text=u'@%s: sorry, command `%s` is only allowed for my admins' % (msg.username, command),
                              as_user=True,
                              link_names=True)
                return

            if command == 'hangouts':
                message = '@%s: list of active hangouts:\n' % msg.username
                for c in self.bot.list_conversations():
                    message += '*%s:* _%s_\n' % (self.bot.conversations.get_name(c, truncate=True), c.id_)
                userID = self.get_slackDM(msg.user)
                self.api_call('chat.postMessage',
                              channel=userID,
                              text=message,
                              as_user=True,
                              link_names=True)

            elif command == 'listsyncs':
                message = '@%s: list of current sync connections with this slack team:\n' % msg.username
                for sync in self.syncs:
                    hangoutname = 'unknown'
                    for c in self.bot.list_conversations():
                        if c.id_ == sync.hangoutid:
                            hangoutname = self.bot.conversations.get_name(c, truncate=False)
                            break
                    channelname = 'unknown'
                    if sync.channelid.startswith('C'):
                        channelname = self.get_channelname(sync.channelid)
                    elif sync.channelid.startswith('G'):
                        channelname = self.get_groupname(sync.channelid)
                    message += '*%s (%s) : %s (%s)* _%s_\n' % (
                        channelname,
                        sync.channelid,
                        hangoutname,
                        sync.hangoutid,
                        sync.getPrintableOptions()
                        )
                userID = self.get_slackDM(msg.user)
                self.api_call('chat.postMessage',
                              channel=userID,
                              text=message,
                              as_user=True,
                              link_names=True)
            elif command == 'syncto':
                message = '@%s: ' % msg.username
                if not len(args):
                    message += u'sorry, but you have to specify a Hangout Id for command `syncto`'
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                hangoutid = args[0]
                shortname = None
                if len(args) > 1:
                    shortname = ' '.join(args[1:])
                hangoutname = None
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = self.bot.conversations.get_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                if not shortname:
                    shortname = hangoutname
                if msg.channel.startswith('D'):
                    channelname = 'DM'
                else:
                    channelname = '#%s' % self.get_channelname(msg.channel)

                try:
                    self.syncto(msg.channel, hangoutid, shortname)
                except AlreadySyncingError:
                    message += u'This channel (%s) is already synced with Hangout _%s_.' % (channelname, hangoutname)
                else:
                    message += u'OK, I will now sync all messages in this channel (%s) with Hangout _%s_.' % (channelname, hangoutname)
                self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)

            elif command == 'disconnect':
                message = '@%s: ' % msg.username
                if not len(args):
                    message += u'sorry, but you have to specify a Hangout Id for command `disconnect`'
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                hangoutid = args[0]
                hangoutname = None
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = self.bot.conversations.get_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                if msg.channel.startswith('D'):
                    channelname = 'DM'
                else:
                    channelname = '#%s' % self.get_channelname(msg.channel)
                try:
                    self.disconnect(msg.channel, hangoutid)
                except NotSyncingError:
                    message += u'This channel (%s) is *not* synced with Hangout _%s_.' % (channelname, hangoutid)
                else:
                    message += u'OK, I will no longer sync messages in this channel (%s) with Hangout _%s_.' % (channelname, hangoutname)
                self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)

            elif command == 'setsyncjoinmsgs':
                message = '@%s: ' % msg.username
                if len(args) != 2:
                    message += u'sorry, but you have to specify a Hangout Id and a `true` or `false` for command `setsyncjoinmsgs`'
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                hangoutid = args[0]
                enable = args[1]
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = self.bot.conversations.get_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                if msg.channel.startswith('D'):
                    channelname = 'DM'
                else:
                    channelname = '#%s' % self.get_channelname(msg.channel)

                if enable.lower() in ['true', 'on', 'y', 'yes']:
                    enable = True
                elif enable.lower() in ['false', 'off', 'n', 'no']:
                    enable = False
                else:
                    message += u'sorry, but "%s" is not "true" or "false"' % enable
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                try:
                    self.setsyncjoinmsgs(msg.channel, hangoutid, enable)
                except NotSyncingError:
                    message += u'This channel (%s) is not synced with Hangout _%s_, not changing syncjoinmsgs.' % (channelname, hangoutname)
                else:
                    message += u'OK, I will %s sync join/leave messages in this channel (%s) with Hangout _%s_.' % (('now' if enable else 'no longer'), channelname, hangoutname)
                self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)

            elif command == 'sethotag':
                message = '@%s: ' % msg.username
                if len(args) < 2:
                    message += u'sorry, but you have to specify a Hangout Id and a tag (or "none") for command `sethotag`'
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                hangoutid = args[0]
                hotag = ' '.join(args[1:])
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = self.bot.conversations.get_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                if msg.channel.startswith('D'):
                    channelname = 'DM'
                else:
                    channelname = '#%s' % self.get_channelname(msg.channel)

                if hotag == "none":
                    hotag = None
                    oktext = '*not* be tagged'
                else:
                    oktext = 'be tagged with " (%s)"' % hotag

                try:
                    self.sethotag(msg.channel, hangoutid, hotag)
                except NotSyncingError:
                    message += u'This channel (%s) is not synced with Hangout _%s_, not changing Hangout tag.' % (channelname, hangoutname)
                else:
                    message += u'OK, messages from Hangout _%s_ will %s in slack channel %s.' % (hangoutname, oktext, channelname)
                self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)

            elif command == 'setimageupload':
                message = '@%s: ' % msg.username
                if len(args) != 2:
                    message += u'sorry, but you have to specify a Hangout Id and a `true` or `false` for command `setimageupload`'
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                hangoutid = args[0]
                upload = args[1]
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = self.bot.conversations.get_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                if msg.channel.startswith('D'):
                    channelname = 'DM'
                else:
                    channelname = '#%s' % self.get_channelname(msg.channel)

                if upload.lower() in ['true', 'on', 'y', 'yes']:
                    upload = True
                elif upload.lower() in ['false', 'off', 'n', 'no']:
                    upload = False
                else:
                    message += u'sorry, but "%s" is not "true" or "false"' % upload
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                try:
                    self.setimageupload(msg.channel, hangoutid, upload)
                except NotSyncingError:
                    message += u'This channel (%s) is not synced with Hangout _%s_, not changing imageupload.' % (channelname, hangoutname)
                else:
                    message += u'OK, I will %s upload images shared in this channel (%s) with Hangout _%s_.' % (('now' if upload else 'no longer'), channelname, hangoutname)
                self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)

            elif command == 'setslacktag':
                message = '@%s: ' % msg.username
                if len(args) < 2:
                    message += u'sorry, but you have to specify a Hangout Id and a tag (or "none") for command `setslacktag`'
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                hangoutid = args[0]
                slacktag = ' '.join(args[1:])
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = self.bot.conversations.get_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                if msg.channel.startswith('D'):
                    channelname = 'DM'
                else:
                    channelname = '#%s' % self.get_channelname(msg.channel)

                if slacktag == "none":
                    slacktag = None
                    oktext = '*not* be tagged'
                else:
                    oktext = 'be tagged with " (%s)"' % slacktag

                try:
                    self.setslacktag(msg.channel, hangoutid, slacktag)
                except NotSyncingError:
                    message += u'This channel (%s) is not synced with Hangout _%s_, not changing Slack tag.' % (channelname, hangoutname)
                else:
                    message += u'OK, messages in this slack channel (%s) will %s in Hangout _%s_.' % (channelname, oktext, hangoutname)
                self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)

            elif command == 'showslackrealnames':
                message = '@%s: ' % msg.username
                if len(args) != 2:
                    message += u'sorry, but you have to specify a Hangout Id and a `true` or `false` for command `showslackrealnames`'
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                hangoutid = args[0]
                realnames = args[1]
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = self.bot.conversations.get_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                if msg.channel.startswith('D'):
                    channelname = 'DM'
                else:
                    channelname = '#%s' % self.get_channelname(msg.channel)

                if realnames.lower() in ['true', 'on', 'y', 'yes']:
                    realnames = True
                elif realnames.lower() in ['false', 'off', 'n', 'no']:
                    realnames = False
                else:
                    message += u'sorry, but "%s" is not "true" or "false"' % upload
                    self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return

                try:
                    self.showslackrealnames(msg.channel, hangoutid, realnames)
                except NotSyncingError:
                    message += u'This channel (%s) is not synced with Hangout _%s_, not changing showslackrealnames.' % (channelname, hangoutname)
                else:
                    message += u'OK, I will display %s when syncing messages from this channel (%s) with Hangout _%s_.' % (('realnames' if realnames else 'usernames'), channelname, hangoutname)
                self.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)


    def syncto(self, channel, hangoutid, shortname):
        for sync in self.syncs:
            if sync.channelid == channel and sync.hangoutid == hangoutid:
                raise AlreadySyncingError

        sync = SlackRTMSync(channel, hangoutid, shortname, self.get_teamname())
        logger.info('adding sync: %s', sync.toDict())
        self.syncs.append(sync)
        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        logger.info('storing sync: %s', sync.toDict())
        syncs.append(sync.toDict())
        self.bot.user_memory_set(self.name, 'synced_conversations', syncs)
        return

    def disconnect(self, channel, hangoutid):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
                logger.info('removing running sync: %s', s)
                self.syncs.remove(s)
        if not sync:
            raise NotSyncingError

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                logger.info('removing stored sync: %s', s)
                syncs.remove(s)
        self.bot.user_memory_set(self.name, 'synced_conversations', syncs)
        return

    def setsyncjoinmsgs(self, channel, hangoutid, enable):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting sync_joins=%s for sync=%s', enable, sync.toDict())
        sync.sync_joins = enable

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed sync_joins', s)
        syncs.append(sync.toDict())
        self.bot.user_memory_set(self.name, 'synced_conversations', syncs)
        return

    def sethotag(self, channel, hangoutid, hotag):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting hotag="%s" for sync=%s', hotag, sync.toDict())
        sync.hotag = hotag

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed hotag', s)
        syncs.append(sync.toDict())
        self.bot.user_memory_set(self.name, 'synced_conversations', syncs)
        return

    def setimageupload(self, channel, hangoutid, upload):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting image_upload=%s for sync=%s', upload, sync.toDict())
        sync.image_upload = upload

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed hotag', s)
        syncs.append(sync.toDict())
        self.bot.user_memory_set(self.name, 'synced_conversations', syncs)
        return

    def setslacktag(self, channel, hangoutid, slacktag):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting slacktag="%s" for sync=%s', slacktag, sync.toDict())
        sync.slacktag = slacktag

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed hotag', s)
        syncs.append(sync.toDict())
        self.bot.user_memory_set(self.name, 'synced_conversations', syncs)
        return

    def showslackrealnames(self, channel, hangoutid, realnames):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting showslackrealnames=%s for sync=%s', realnames, sync.toDict())
        sync.showslackrealnames = realnames

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed hotag', s)
        syncs.append(sync.toDict())
        self.bot.user_memory_set(self.name, 'synced_conversations', syncs)
        return

    @staticmethod
    def _repeater_cleaner(bot, event, id):
        event_tokens = event.text.split(":", maxsplit=1)
        event_text = event_tokens[1].strip()
        if event_text.lower().startswith(tuple([cmd.lower() for cmd in bot._handlers.bot_command])):
            event_text = bot._handlers.bot_command[0] + " [REDACTED]"
        event.text = event_text
        event.from_bot = False
        event._slackrtm_no_repeat = True
        event._external_source = event_tokens[0].strip() + "@slackrtm"

    def handle_reply(self, reply):
        try:
            msg = SlackMessage(self, reply)
            msg_html = self.textToHtml(msg.text)
        except ParseError as e:
            return
        except Exception as e:
            logger.exception('error parsing Slack reply: %s(%s)', type(e), str(e))
            return

        try:
            self.handleCommands(msg)
        except Exception as e:
            logger.exception('error in handleCommands: %s(%s)', type(e), str(e))

        for sync in self.get_syncs(channelid=msg.channel):
            if not sync.sync_joins and msg.is_joinleave:
                continue
            if msg.from_ho_id != sync.hangoutid:
                slacktag = ''
                if sync.slacktag and msg.tag_from_slack:
                    slacktag = ' (%s)' % sync.slacktag
                response = u'<b>%s%s%s:</b> %s' % (msg.realname4ho if sync.showslackrealnames else msg.username4ho, slacktag, msg.edited, msg_html)
                logger.debug('forwarding to HO %s: %s', sync.hangoutid, response.encode('utf-8'))
                if msg.file_attachment:
                    if sync.image_upload:
                        self.loop.call_soon_threadsafe(asyncio.async, self.upload_image(sync.hangoutid, msg.file_attachment))
                        self.lastimg = os.path.basename(msg.file_attachment)
                    else:
                        # we should not upload the images, so we have to send the url instead
                        response += msg.file_attachment
                self.loop.call_soon_threadsafe(asyncio.async,
                    self.bot.coro_send_message(
                        sync.hangoutid, response,
                        context = {
                            'base': {
                                'tags': ['slack', 'relay'],
                                'source': 'slackrtm',
                                'importance': 50
                            },
                            'reprocessor': self.bot.call_shared("reprocessor.attach_reprocessor",
                                self._repeater_cleaner, return_as_dict=True)
                        }
                    )
                )

    @asyncio.coroutine
    def handle_ho_message(self, event):
        if "_slackrtm_no_repeat" in dir(event) and event._slackrtm_no_repeat:
            return

        for sync in self.get_syncs(hangoutid=event.conv_id):
            if self.lastimg and self.lastimg in event.text:
                # already seen this image, skip
                self.lastimg = ''
                return
            fullname = event.user.full_name
            if sync.hotag:
                fullname = '%s (%s)' % (fullname, sync.hotag)
            try:
                photo_url = "http:"+self.bot._user_list.get_user(event.user_id).photo_url
            except Exception as e:
                logger.exception('error while getting user from bot: %s', e)
                photo_url = ''
            message = chatMessageEvent2SlackText(event.conv_event)
            message = u'%s <ho://%s/%s| >' % (message, event.conv_id, event.user_id.chat_id)
            logger.debug("sending to channel %s: %s", sync.channelid, message.encode('utf-8'))
            self.api_call('chat.postMessage',
                          channel=sync.channelid,
                          text=message,
                          username=fullname,
                          link_names=True,
                          icon_url=photo_url)

    def handle_ho_membership(self, event):
        # Generate list of added or removed users
        links = []
        for user_id in event.conv_event.participant_ids:
            user = event.conv.get_user(user_id)
            links.append(u'<https://plus.google.com/%s/about|%s>' % (user.id_.chat_id, user.full_name))
        names = u', '.join(links)

        for sync in self.get_syncs(hangoutid=event.conv_id):
            if not sync.sync_joins:
                continue
            if sync.hotag:
                honame = sync.hotag
            else:
                honame = self.bot.conversations.get_name(event.conv)
            # JOIN
            if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
                invitee = u'<https://plus.google.com/%s/about|%s>' % (event.user_id.chat_id, event.user.full_name)
                if invitee == names:
                    message = u'%s has joined %s' % (invitee, honame)
                else:
                    message = u'%s has added %s to %s' % (invitee, names, honame)
            # LEAVE
            else:
                message = u'%s has left _%s_' % (names, honame)
            message = u'%s <ho://%s/%s| >' % (message, event.conv_id, event.user_id.chat_id)
            logger.debug("sending to channel/group %s: %s", sync.channelid, message)
            self.api_call('chat.postMessage',
                          channel=sync.channelid,
                          text=message,
                          as_user=True,
                          link_names=True)

    def handle_ho_rename(self, event):
        name = self.bot.conversations.get_name(event.conv, truncate=False)

        for sync in self.get_syncs(hangoutid=event.conv_id):
            invitee = u'<https://plus.google.com/%s/about|%s>' % (event.user_id.chat_id, event.user.full_name)
            hotagaddendum = ''
            if sync.hotag:
                hotagaddendum = ' _%s_' % sync.hotag
            message = u'%s has renamed the Hangout%s to _%s_' % (invitee, hotagaddendum, name)
            message = u'%s <ho://%s/%s| >' % (message, event.conv_id, event.user_id.chat_id)
            logger.debug("sending to channel/group %s: %s", sync.channelid, message)
            self.api_call('chat.postMessage',
                          channel=sync.channelid,
                          text=message,
                          as_user=True,
                          link_names=True)


_slackrtms = []


class SlackRTMThread(threading.Thread):
    def __init__(self, bot, loop, config):
        super(SlackRTMThread, self).__init__()
        self._stop = threading.Event()
        self._bot = bot
        self._loop = loop
        self._config = config
        self._listener = None

    def run(self):
        logger.debug('SlackRTMThread.run()')
        asyncio.set_event_loop(self._loop)
        global _slackrtms

        try:
            if self._listener and self._listener in _slackrtms:
                _slackrtms.remove(self._listener)
            self._listener = SlackRTM(self._config, self._bot, self._loop, threaded=True)
            _slackrtms.append(self._listener)
            last_ping = int(time.time())
            while True:
                if self.stopped():
                    return
                replies = self._listener.rtm_read()
                if replies:
                    if 'type' in replies[0]:
                        if replies[0]['type'] == 'hello':
                        # print('slackrtm: ignoring first replies including type=hello message to avoid message duplication: %s...' % str(replies)[:30])
                            continue
                    for reply in replies:
                        try:
                            self._listener.handle_reply(reply)
                        except Exception as e:
                            logger.exception('error during handle_reply(): %s\n%s', str(e), pprint.pformat(reply))
                now = int(time.time())
                if now > last_ping + 30:
                    self._listener.ping()
                    last_ping = now
                time.sleep(.1)
        except KeyboardInterrupt:
            # close, nothing to do
            return
        except WebSocketConnectionClosedException as e:
            logger.exception('WebSocketConnectionClosedException(%s)', str(e))
            return self.run()
        except IncompleteLoginError:
            logger.exception('IncompleteLoginError, restarting')
            time.sleep(1)
            return self.run()
        except (ConnectionFailedError, TimeoutError):
            logger.exception('Connection failed or Timeout, waiting 10 sec trying to restart')
            time.sleep(10)
            return self.run()
        except ConnectionResetError:
            logger.exception('ConnectionResetError, attempting to restart')
            time.sleep(1)
            return self.run()
        except Exception as e:
            logger.exception('SlackRTMThread: unhandled exception: %s', str(e))
        return

    def stop(self):
        global _slackrtms
        if self._listener and self._listener in _slackrtms:
            _slackrtms.remove(self._listener)
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()


def _initialise(bot):
    # Start and asyncio event loop
    loop = asyncio.get_event_loop()
    slack_sink = bot.get_config_option('slackrtm')
    threads = []
    if isinstance(slack_sink, list):
        for sinkConfig in slack_sink:
            # start up slack listener in a separate thread
            t = SlackRTMThread(bot, loop, sinkConfig)
            t.daemon = True
            t.start()
            threads.append(t)
    logger.info("%d sink thread(s) started", len(threads))

    plugins.register_handler(_handle_slackout, type="allmessages")
    plugins.register_handler(_handle_membership_change, type="membership")
    plugins.register_handler(_handle_rename, type="rename")

    plugins.register_admin_command(["slack_help", "slacks", "slack_channels", "slack_listsyncs", "slack_syncto", "slack_disconnect", "slack_setsyncjoinmsgs", "slack_setimageupload", "slack_sethotag","slack_users", "slack_setslacktag", "slack_showslackrealnames"])


@asyncio.coroutine
def _handle_slackout(bot, event, command):
    for slackrtm in _slackrtms:
        try:
            yield from slackrtm.handle_ho_message(event)
        except Exception as e:
            logger.exception('_handle_slackout threw: %s', str(e))


@asyncio.coroutine
def _handle_membership_change(bot, event, command):
    for slackrtm in _slackrtms:
        try:
            slackrtm.handle_ho_membership(event)
        except Exception as e:
            logger.exception('_handle_membership_change threw: %s', str(e))


@asyncio.coroutine
def _handle_rename(bot, event, command):
    if not _slackrtms:
        return
    for slackrtm in _slackrtms:
        try:
            slackrtm.handle_ho_rename(event)
        except Exception as e:
            logger.exception('_handle_rename threw: %s', str(e))


def slacks(bot, event, *args):
    """list all configured slack teams

       usage: /bot slacks"""

    segments = [
        hangups.ChatMessageSegment('Configured Slack teams:', is_bold=True),
        hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
        ]
    for slackrtm in _slackrtms:
        segments.append(hangups.ChatMessageSegment('%s' % slackrtm.name))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    bot.send_message_segments(event.conv, segments)




def slack_channels(bot, event, *args):
    """list all slack channels available in specified slack team

    usage: /bot slack_channels <teamname>"""

    if len(args) != 1:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name to list channels of', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return

    segments = []

    segments.append(hangups.ChatMessageSegment('Slack channels in team %s:' % (slackname), is_bold=True))
    segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    slackrtm.update_channelinfos()
    for cid in slackrtm.channelinfos:
        if not slackrtm.channelinfos[cid]['is_archived']:
            segments.append(hangups.ChatMessageSegment('%s (%s)' % (slackrtm.channelinfos[cid]['name'], cid)))
            segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))

    segments.append(hangups.ChatMessageSegment('private groups:', is_bold=True))
    segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    slackrtm.update_groupinfos()
    for gid in slackrtm.groupinfos:
        if not slackrtm.groupinfos[gid]['is_archived']:
            segments.append(hangups.ChatMessageSegment('%s (%s)' % (slackrtm.groupinfos[gid]['name'], gid)))
            segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))

    bot.send_message_segments(event.conv, segments)

def slack_users(bot, event, *args):
    """list all slack channels available in specified slack team

        usage: /bot slack_users <team> <channel>"""

    if len(args) >= 3:
        honame = ' '.join(args[2:])
    else:
        if len(args) != 2:
            bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name and a channel', is_bold=True)])
            return
        honame = bot.conversations.get_name(event.conv)

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return
    slackrtm.update_channelinfos()
    channelid = args[1]
    channelname = slackrtm.get_groupname(channelid, slackrtm.get_channelname(channelid))
    if not channelname:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a channel with id "%s" in team "%s", use /bot slack_channels %s to list all teams' % (channelid, slackname, slackname), is_bold=True)])
        return

    segments = []

    segments.append(hangups.ChatMessageSegment('Slack users in channel %s:' % (channelname), is_bold=True))
    segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    users = slackrtm.get_channel_users(channelid)
    for username, realname in sorted(users.items()):
        segments.append(hangups.ChatMessageSegment('%s (%s)' % (realname, username)))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))

    bot.send_message_segments(event.conv, segments)


def slack_listsyncs(bot, event, *args):
    """list current conversations we are syncing

    usage: /bot slack_listsyncs"""

    segments = [
        hangups.ChatMessageSegment('list of currently synced conversations:', is_bold=True),
        hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)
        ]
    for slackrtm in _slackrtms:
        for sync in slackrtm.syncs:
            hangoutname = 'unknown'
            for c in bot.list_conversations():
                if c.id_ == sync.hangoutid:
                    hangoutname = bot.conversations.get_name(c, truncate=False)
                    break
            segments.extend(
                [
                    hangups.ChatMessageSegment(
                        '%s:%s(%s) : %s(%s)' % (
                            slackrtm.name,
                            slackrtm.get_channelname(sync.channelid),
                            sync.channelid,
                            hangoutname,
                            sync.hangoutid
                            ),
                        is_bold=True
                        ),
                    hangups.ChatMessageSegment(' '),
                    hangups.ChatMessageSegment(sync.getPrintableOptions(), is_italic=True),
                    hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                    ]
                )

    bot.send_message_segments(event.conv, segments)


def slack_syncto(bot, event, *args):
    """start syncing the current hangout to a given slack team/channel

    usage: /bot slack_syncto <teamname> <channelid>"""

    if len(args) >= 3:
        honame = ' '.join(args[2:])
    else:
        if len(args) != 2:
            bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name and a channel', is_bold=True)])
            return
        honame = bot.conversations.get_name(event.conv)

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return

    channelid = args[1]
    channelname = slackrtm.get_groupname(channelid, slackrtm.get_channelname(channelid))
    if not channelname:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a channel with id "%s" in team "%s", use /bot slack_channels %s to list all teams' % (channelid, slackname, slackname), is_bold=True)])
        return

    try:
        slackrtm.syncto(channelid, event.conv.id_, honame)
    except AlreadySyncingError:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('Already syncing this Hangout to %s:%s.' % (slackname, channelname), is_bold=True)])
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('OK, I will now sync all messages in this Hangout to %s:%s.' % (slackname, channelname), is_bold=True)])


def slack_disconnect(bot, event, *args):
    """stop syncing the current hangout with given slack team and channel

    usage: /bot slack_disconnect <teamname> <channelid>"""

    if len(args) != 2:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name and a channel', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return

    channelid = args[1]
    channelname = slackrtm.get_groupname(channelid, slackrtm.get_channelname(channelid))
    if not channelname:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a channel with id "%s" in team "%s", use /bot slack_channels %s to list all teams' % (channelid, slackname, slackname), is_bold=True)])
        return

    try:
        slackrtm.disconnect(channelid, event.conv.id_)
    except NotSyncingError:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('This Hangout is NOT synced to %s:%s.' % (slackname, channelname), is_bold=True)])
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('OK, I will no longer sync messages in this Hangout to %s:%s.' % (slackname, channelname), is_bold=True)])


def slack_setsyncjoinmsgs(bot, event, *args):
    """enable or disable sending notifications any time someone joins/leaves/adds/invites/kicks

    usage: /bot slack_setsyncjoinmsgs <teamname> <channelid> {true|false}"""

    if len(args) != 3:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name, a channel and "true" or "false"', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return

    channelid = args[1]
    channelname = slackrtm.get_groupname(channelid, slackrtm.get_channelname(channelid))
    if not channelname:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a channel with id "%s" in team "%s", use /bot slack_channels %s to list all teams' % (channelid, slackname, slackname), is_bold=True)])
        return

    enable = args[2]
    if enable.lower() in ['true', 'on', 'y', 'yes']:
        enable = True
    elif enable.lower() in ['false', 'off', 'n', 'no']:
        enable = False
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('sorry, but "%s" is not "true" or "false"' % enable, is_bold=True)])
        return

    try:
        slackrtm.setsyncjoinmsgs(channelid, event.conv.id_, enable)
    except NotSyncingError:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('This Hangout is NOT synced to %s:%s.' % (slackname, channelname), is_bold=True)])
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('OK, I will %s sync join/leave messages in this Hangout with %s:%s.' % (('now' if enable else 'no longer'), slackname, channelname), is_bold=True)])


def slack_setimageupload(bot, event, *args):
    """enable/disable image upload between the synced conversations (default: enabled)

    usage: /bot slack_setimageupload <teamname> <channelid> {true|false}"""

    if len(args) != 3:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name, a channel and "true" or "false"', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return

    channelid = args[1]
    channelname = slackrtm.get_groupname(channelid, slackrtm.get_channelname(channelid))
    if not channelname:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a channel with id "%s" in team "%s", use /bot slack_channels %s to list all teams' % (channelid, slackname, slackname), is_bold=True)])
        return

    upload = args[2]
    if upload.lower() in ['true', 'on', 'y', 'yes']:
        upload = True
    elif upload.lower() in ['false', 'off', 'n', 'no']:
        upload = False
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('sorry, but "%s" is not "true" or "false"' % upload, is_bold=True)])
        return

    try:
        slackrtm.setimageupload(channelid, event.conv.id_, upload)
    except NotSyncingError:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('This Hangout is NOT synced to %s:%s.' % (slackname, channelname), is_bold=True)])
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('OK, I will %s upload images to this Hangout when shared in %s:%s.' % (('now' if upload else 'no longer'), slackname, channelname), is_bold=True)])


def slack_sethotag(bot, event, *args):
    """sets the identity of current hangout when syncing this conversation
    (default: title of this hangout when sync was set up, use 'none' to disable tagging)

    usage: /bot slack_hotag <teamname> <channelid> {<tag>|none}"""

    if len(args) < 3:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name, a channel and a tag', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return

    channelid = args[1]
    channelname = slackrtm.get_groupname(channelid, slackrtm.get_channelname(channelid))
    if not channelname:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a channel with id "%s" in team "%s", use /bot slack_channels %s to list all teams' % (channelid, slackname, slackname), is_bold=True)])
        return

    hotag = ' '.join(args[2:])
    if hotag == 'none':
        hotag = None
        oktext = 'NOT be tagged'
    else:
        oktext = 'be tagged with " (%s)"' % hotag

    try:
        slackrtm.sethotag(channelid, event.conv.id_, hotag)
    except NotSyncingError:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('This Hangout is NOT synced to %s:%s.' % (slackname, channelname), is_bold=True)])
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('OK, messages from this Hangout will %s in slack channel  %s:%s.' % (oktext, slackname, channelname), is_bold=True)])

def slack_setslacktag(bot, event, *args):
    """sets the identity of the specified slack conversation synced to the current hangout
    (default: name of the slack team, use 'none' to disable tagging)

    usage: /bot slack_slacktag <teamname> <channelid> {<tag>|none}"""

    if len(args) < 3:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name, a channel and a tag', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return

    channelid = args[1]
    channelname = slackrtm.get_groupname(channelid, slackrtm.get_channelname(channelid))
    if not channelname:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a channel with id "%s" in team "%s", use /bot slack_channels %s to list all teams' % (channelid, slackname, slackname), is_bold=True)])
        return

    slacktag = ' '.join(args[2:])
    if slacktag == 'none':
        slacktag = None
        oktext = 'NOT be tagged'
    else:
        oktext = 'be tagged with " (%s)"' % slacktag

    try:
        slackrtm.setslacktag(channelid, event.conv.id_, slacktag)
    except NotSyncingError:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('This Hangout is NOT synced to %s:%s.' % (slackname, channelname), is_bold=True)])
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('OK, messages from slack channel %s:%s will %s in this Hangout.' % (oktext, slackname, channelname), is_bold=True)])



def slack_showslackrealnames(bot, event, *args):
    """enable/disable display of realnames instead of usernames in messages synced from slack
    (default: disabled)

    usage: /bot slack_showslackrealnames <teamname> <channelid> {true|false}"""

    if len(args) != 3:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name, a channel and "true" or "false"', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in _slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return

    channelid = args[1]
    channelname = slackrtm.get_groupname(channelid, slackrtm.get_channelname(channelid))
    if not channelname:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a channel with id "%s" in team "%s", use /bot slack_channels %s to list all teams' % (channelid, slackname, slackname), is_bold=True)])
        return

    realnames = args[2]
    if realnames.lower() in ['true', 'on', 'y', 'yes']:
        realnames = True
    elif realnames.lower() in ['false', 'off', 'n', 'no']:
        realnames = False
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('sorry, but "%s" is not "true" or "false"' % realnames, is_bold=True)])
        return

    try:
        slackrtm.showslackrealnames(channelid, event.conv.id_, realnames)
    except NotSyncingError:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('This Hangout is NOT synced to %s:%s.' % (slackname, channelname), is_bold=True)])
    else:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('OK, I will display %s in this Hangout when syncing from %s:%s.' % (('realnames' if realnames else 'usernames'), slackname, channelname), is_bold=True)])
