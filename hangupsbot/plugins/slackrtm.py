import time
import re
import os
import pprint
import traceback

import threading
import hangups.ui.utils
try:
    # for a python3 compatible slackclient, please use https://github.com/mlaferrera/python-slackclient.git
    from slackclient import SlackClient
except Exception as e:
    print('Please install https://github.com/mlaferrera/python-slackclient.git for a Python3 compatible slackclient')
    raise e
try:
    from websocket import WebSocketConnectionClosedException
except Exception as e:
    print('Please install websocket: pip3 install websocket')
    raise e

import asyncio
import logging
import hangups
import json

try:
    import emoji
    if 'decode' in dir(emoji):
        def emoji_decode(char):
            return emoji.decode(char)
    else:
        # stolen from emoji-0.3.3
        def emoji_decode(u_code):
            # for the moment, we return the unicode character as-is as there seems to be many incompatible mappings for slack in the newer emoji module
            return u_code
#            try:
#                u_code = u_code.decode('utf-8')
#            except:
#                pass
#
#            try:
#                textemoji = emoji.UNICODE_EMOJI_ALIAS[u_code]
#                slack_emoji_mapping = {
#                    ':smiling_face_with_halo:': ':innocent',
#                    }
#                if textemoji in slack_emoji_mapping:
#                    textemoji = slack_emoji_mapping[textemoji]
#                return textemoji
#            except KeyError:
#                raise ValueError("Unicode code is not an emoji: %s" % u_code)

        # basic "simple_smile" support on request of @alvin853
        emoji.EMOJI_UNICODE[':simple_smile:'] = emoji.EMOJI_UNICODE[':white_smiling_face:']
        emoji.EMOJI_ALIAS_UNICODE[':simple_smile:'] = emoji.EMOJI_UNICODE[':white_smiling_face:']
except Exception as e:
    print('Please install emoji: pip3 install emoji>=0.3.3')
    raise e

import urllib
#import slacker

""" SlackRTM plugin for listening to hangouts and slack and syncing messages between the two.
config.json will have to be configured as follows:
"slackrtm": [{
  "name": "SlackNameForLoggingCommandsEtc",
  "key": "SLACK_API_KEY",
  "admins": [
    "U01",
    "U02"
  ]
}]

You can (theoretically) set up as many slack sinks per bot as you like, by extending the list"""


def unicodeemoji2text(text):
    out = u''
    for c in text[:]:
        try:
            c = emoji_decode(c)
        except:
            pass
        out = out + c
    return out

def chatMessageEvent2SlackText(event):
    def renderTextSegment(segment):
        out = ''
        if segment.is_bold:
            out += ' *'
        if segment.is_italic:
            out += ' _'
        out += unicodeemoji2text(segment.text)
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
            # unfortunately slack does not format links :-(
            lines[-1] += segment.text
        elif segment.type_ == hangups.schemas.SegmentType.LINE_BREAK:
            lines.append('')
        else:
            print('slackrtm: Ignoring unknown chat message segment type: %s' % segment.type_)
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
        self.edited = None
        self.from_ho_id = None
        self.sender_id = None
        self.channel = None
        self.file_attachment = None

        if not 'type' in reply:
            print("slackrtm: No 'type' in reply:")
            print("slackrtm: "+str(reply))
            raise ParseError('No "type" in reply:\n%s' % str(reply))
    
        if reply['type'] in ['pong', 'presence_change',  'user_typing', 'file_shared', 'file_public', 'file_comment_added', 'file_comment_deleted', 'message_deleted']:
            # we ignore pong's as they are only answers for our pings
            raise ParseError('Not a "message" type reply: type=%s' % reply['type'])

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
                edited = '(msgupd)'
                user = reply['message']['edited']['user']
                text = reply['message']['text']
            else:
                # sent images from HO got an additional message_changed subtype without an 'edited' when slack renders the preview
                if 'username' in reply['message']:
                    # we ignore them as we already got the (unedited) message
                    raise ParseError('ignore "edited" message from bot, possibly slack-added preview')
                else:
                    print('slackrtm: unable to handle this kind of strange message type:\n%s' % pprint.pformat(reply))
                    raise ParseError('strange edited message without "edited" member:\n%s' % str(reply))
        elif reply['type'] == 'message' and 'subtype' in reply and reply['subtype'] == 'file_comment':
            user = reply['comment']['user']
            text = reply['text']
        elif reply['type'] == 'file_comment_added':
            user = reply['comment']['user']
            text = reply['comment']['comment']
        else:
            if reply['type'] == 'message' and 'subtype' in reply and reply['subtype'] == 'bot_message' and not 'user' in reply:
                is_bot = True
                # this might be a HO relayed message, check if username is set and use it as username
                username = reply['username']
            elif not 'text' in reply or not 'user' in reply:
                print("slackrtm: no text/user in reply:\n%s" % str(reply))
                raise ParseError('no text/user in reply:\n%s' % str(reply))
            else:
                user = reply['user']
            if not 'text' in reply:
                # IFTTT?
                if 'attachments' in reply and 'text' in reply['attachments'][0]:
                    text = reply['attachments'][0]['text']
                else:
                    print('slackrtm: strange message without text and attachments:\n%s' % pprint.pformat(reply))
            else:
                text = reply['text']
        file_attachment = None
        if 'file' in reply:
            if 'url' in reply['file']:
                file_attachment = reply['file']['url']

        # now we check if the message has the hidden ho relay tag, extract and remove it
        hoidfmt = re.compile(r'^(.*) <ho://([^/]+)/([^|]+)\| >$', re.MULTILINE|re.DOTALL)
        match = hoidfmt.match(text)
        if match:
            text = match.group(1)
            from_ho_id = match.group(2)
            sender_id = match.group(3)
            if 'googleusercontent.com' in text:
                gucfmt = re.compile(r'^(.*)<(https?://[^\s/]*googleusercontent.com/[^\s]*)>$', re.MULTILINE|re.DOTALL)
                match = gucfmt.match(text)
                if match:
                    text = match.group(1)
                    file_attachment = match.group(2)

        username4ho = username
        if not is_bot:
            username = slackrtm.get_username(user, user)
            username4ho = u'%s (Slack)' % username
        elif sender_id != '':
            username4ho = u'<a href="https://plus.google.com/%s">%s</a>' % (sender_id, username)

        if 'channel' in reply:
            channel = reply['channel']
        elif 'group' in reply:
            channel = reply['group']
        if not channel:
            print('slackrtm: no channel or group in reply: %s' % pprint.pformat(reply))
            raise ParseError('no channel found in reply:\n%s' % str(reply))

        if reply['type'] == 'message' and 'subtype' in reply and reply['subtype'] in [ 'channel_join', 'channel_leave', 'group_join', 'group_leave' ]:
            is_joinleave = True

        self.text = text
        self.user = user
        self.username = username
        self.username4ho = username4ho
        self.edited = edited
        self.from_ho_id = from_ho_id
        self.sender_id = sender_id
        self.channel = channel
        self.file_attachment = file_attachment
        self.is_joinleave = is_joinleave


class SlackRTMSync(object):
    def __init__(self, channelid, hangoutid, hotag, sync_joins=True, image_upload=True):
        self.channelid = channelid
        self.hangoutid = hangoutid
        self.hotag = hotag
        self.sync_joins = sync_joins
        self.image_upload = image_upload

    def fromDict(sync_dict):
        sync_joins = True
        if 'sync_joins' in sync_dict and not sync_dict['sync_joins']:
            sync_joins = False
        image_upload = True
        if 'image_upload' in sync_dict and not sync_dict['image_upload']:
            image_upload = False
        return SlackRTMSync(sync_dict['channelid'], sync_dict['hangoutid'], sync_dict['hotag'], sync_joins)

    def toDict(self):
        return {
            'channelid': self.channelid,
            'hangoutid': self.hangoutid,
            'hotag': self.hotag,
            'sync_joins': self.sync_joins,
            'image_upload': self.image_upload,
            }

    def getPrintableOptions(self):
        return 'hotag="%s", sync_joins=%s, image_upload=%s' % (
            self.hotag if self.hotag else 'NONE',
            self.sync_joins,
            self.image_upload,
            )

class SlackRTM(object):
    def __init__(self, sink_config, bot, loop, threaded=False):
        self.bot = bot
        self.loop = loop
        self.config = sink_config
        self.apikey = self.config['key']
        self.threadname = None

        self.slack = SlackClient(self.apikey)
        if not self.slack.rtm_connect():
            raise ConnectionFailedError
        for key in [ 'self' , 'team', 'users', 'channels', 'groups' ]:
            if not key in self.slack.server.login_data:
                raise IncompleteLoginError
        if threaded:
            if 'name' in self.config:
                self.name = self.config['name']
            else:
                self.name = '%s@%s' % (self.slack.server.login_data['self']['name'], self.slack.server.login_data['team']['domain'])
                print('slackrtm: WARNING: no name set in config file, using computed name %s' % self.name)
            self.threadname = 'SlackRTM:' + self.name
            threading.current_thread().name = self.threadname
            print('slackrtm: Started RTM connection for SlackRTM thread %s' % pprint.pformat(threading.current_thread()))
            for t in threading.enumerate():
                if t.name == self.threadname and t != threading.current_thread():
                    print('slackrtm: Old thread found: %s - killing it' % pprint.pformat(t))
                    t.stop()
            
        self.update_usernames(self.slack.server.login_data['users'])
        self.update_channelnames(self.slack.server.login_data['channels'])
        self.update_groupnames(self.slack.server.login_data['groups'])
        self.my_uid = self.slack.server.login_data['self']['id']

        self.admins = []
        if 'admins' in self.config:
            for a in self.config['admins']:
                if not a in self.usernames:
                    print('slackrtm: WARNING: userid %s not found in user list, ignoring' % a)
                else:
                    self.admins.append(a)
        if not len(self.admins):
            print('slackrtm: WARNING: no admins specified in config file, some commands will not work for any slack user')

        self.hangoutids = {}
        self.hangoutnames = {}
        for c in self.bot.list_conversations():
            name = hangups.ui.utils.get_conv_name(c, truncate=True)
            self.hangoutids[ name ] = c.id_
            self.hangoutnames[ c.id_ ] = name

        self.syncs = []
        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            self.syncs.append( SlackRTMSync.fromDict(s) )
        if 'synced_conversations' in self.config and len(self.config['synced_conversations']):
            print('slackrtm: WARNING: defining synced_conversations in config is deprecated!')
            for conv in self.config['synced_conversations']:
                if len(conv) == 3:
                    hotag = conv[2]
                else:
                    if not conv[1] in self.hangoutnames:
                        print("slackrtm: could not find conv %s in bot's conversations, but used in (deprecated) synced_conversations in config!" % conv[1])
                        hotag = conv[1]
                    else:
                        hotag = self.hangoutnames[ conv[1] ]
                self.syncs.append( SlackRTMSync(conv[0], conv[1], hotag) )

    def update_usernames(self, users=None):
        if users is None:
            response = json.loads(self.slack.api_call('users.list').decode("utf-8"))
            users = response['members']
        usernames = {}
        for u in users:
            usernames[u['id']] = u['name']
        self.usernames = usernames

    def get_username(self, user, default=None):
        if not user in self.usernames:
            print('slackrtm: user not found, reloading users...')
            self.update_usernames()
            if not user in self.usernames:
                print('slackrtm: could not find user "%s" although reloaded' % user)
                return default
        return self.usernames[user]

    def update_channelnames(self, channels=None):
        if channels is None:
            response = json.loads(self.slack.api_call('channels.list').decode("utf-8"))
            channels = response['channels']
        channelnames = {}
        for c in channels:
            channelnames[c['id']] = c['name']
        self.channelnames = channelnames

    def get_channelname(self, channel, default=None):
        if not channel in self.channelnames:
            print('slackrtm: channel not found, reloading channels...')
            self.update_channelnames()
            if not channel in self.channelnames:
                print('slackrtm: could not find channel "%s" although reloaded' % channel)
                return default
        return self.channelnames[channel]

    def update_groupnames(self, groups=None):
        if groups is None:
            response = json.loads(self.slack.api_call('groups.list').decode("utf-8"))
            groups = response['groups']
        groupnames = {}
        for c in groups:
            groupnames[c['id']] = c['name']
        self.groupnames = groupnames

    def get_groupname(self, group, default=None):
        if not group in self.groupnames:
            print('slackrtm: group not found, reloading groups...')
            self.update_groupnames()
            if not group in self.groupnames:
                print('slackrtm: could not find group "%s" although reloaded' % group)
                return default
        return self.groupnames[group]

    def get_syncs(self, channelid = None, hangoutid = None):
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
        reffmt = re.compile('<((.)([^|>]*))((\|)([^>]*)|([^>]*))>')
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
        text = text.replace("\n", " <br/>\n")
        if text[0] == ' ' and text[-1] == ' ':
            text = text[1:-1]
        else:
            print('slackrtm: something went wrong while formating text, leading or trailing space missing: "%s"' % text)
        return text

    @asyncio.coroutine
    def upload_image(self, hoid, image):
        try:
            print('Downloading %s' % image)
            filename = os.path.basename(image)
            image_response = urllib.request.urlopen(image)
            print('Uploading as %s' % filename)
            image_id = yield from self.bot._client.upload_image(image_response, filename=filename)
            print('Sending HO message, image_id: %s' % image_id)
            self.bot.send_message_segments(hoid, None, image_id=image_id)
        except Exception as e:
            print('slackrtm: Exception in upload_image: %s(%s)' % (type(e), str(e)))
            traceback.print_exc()

    def handleCommands(self, msg):
        cmdfmt = re.compile(r'^<@'+self.my_uid+'>:?\s+(help|whereami|whoami|whois|admins|hangoutmembers|hangouts|listsyncs|syncto|disconnect|setsyncjoinmsgs|sethotag|setimageupload)', re.IGNORECASE)
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
            self.slack.api_call('chat.postMessage',
                                channel=msg.channel,
                                text=message,
                                as_user=True,
                                link_names=True)

        elif command == 'whereami':
            self.slack.api_call('chat.postMessage',
                                channel=msg.channel,
                                text=u'@%s: you are in channel %s' % (msg.username, msg.channel),
                                as_user=True,
                                link_names=True)

        elif command == 'whoami':
            
            self.slack.api_call('chat.postMessage',
                                channel=msg.channel,
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
                    for id in self.usernames:
                        if self.usernames[id] == user:
                            user = id
                            break
                if not user.startswith('U'):
                    message = u'%s: sorry, but I could not find user _%s_ in this slack.' % (msg.username, user)
                else:
                    message = u'@%s: the user id of _%s_ is %s' % (msg.username, self.get_username(user), user)
            self.slack.api_call('chat.postMessage',
                                channel=msg.channel,
                                text=message,
                                as_user=True,
                                link_names=True)

        elif command == 'admins':
            message = '@%s: my admins are:\n' % msg.username
            for a in self.admins:
                message += '@%s: _%s_\n' % (self.get_username(a), a)
            self.slack.api_call('chat.postMessage',
                                channel=msg.channel,
                                text=message,
                                as_user=True,
                                link_names=True)

        elif command == 'hangoutmembers':
            message = '@%s: the following users are in the synced Hangout(s):\n' % msg.username
            for sync in self.get_syncs(channelid = msg.channel):
                hangoutname = 'unknown'
                conv = None
                for c in self.bot.list_conversations():
                    if c.id_ == sync.hangoutid:
                        conv = c
                        hangoutname = hangups.ui.utils.get_conv_name(c, truncate=False)
                        break
                message += '%s aka %s (%s):\n' % (hangoutname, sync.hotag if sync.hotag else 'untagged', sync.hangoutid)
                for u in conv.users:
                    message += ' + <https://plus.google.com/%s|%s>\n' % (u.id_.gaia_id, u.full_name)
            self.slack.api_call('chat.postMessage',
                                channel=msg.channel,
                                text=message,
                                as_user=True,
                                link_names=True)

        else:
            # the remaining commands are for admins only
            if not msg.user in self.admins:
                self.slack.api_call('chat.postMessage',
                                    channel=msg.channel,
                                    text=u'@%s: sorry, command `%s` is only allowed for my admins' % (msg.username, command),
                                    as_user=True,
                                    link_names=True)
                return
    
            if command == 'hangouts':
                message = '@%s: list of active hangouts:\n' % msg.username
                for c in self.bot.list_conversations():
                    message += '*%s:* _%s_\n' % (hangups.ui.utils.get_conv_name(c, truncate=True), c.id_)
                self.slack.api_call('chat.postMessage',
                                    channel=msg.channel,
                                    text=message,
                                    as_user=True,
                                    link_names=True)
    
            elif command == 'listsyncs':
                message = '@%s: list of current sync connections with this slack team:\n' % msg.username
                for sync in self.syncs:
                    hangoutname = 'unknown'
                    for c in self.bot.list_conversations():
                        if c.id_ == sync.hangoutid:
                            hangoutname = hangups.ui.utils.get_conv_name(c, truncate=False)
                            break
                    message += '*%s(%s) : %s(%s)* _%s_\n' % (
                        self.get_channelname(sync.channelid),
                        sync.channelid,
                        hangoutname,
                        sync.hangoutid,
                        sync.getPrintableOptions()
                        )
                self.slack.api_call('chat.postMessage',
                                    channel=msg.channel,
                                    text=message,
                                    as_user=True,
                                    link_names=True)
    
            elif command == 'syncto':
                message = '@%s: ' % msg.username
                if not len(args):
                    message += u'sorry, but you have to specify a Hangout Id for command `syncto`'
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return
    
                hangoutid = args[0]
                shortname = None
                if len(args) > 1:
                    shortname = ' '.join(args[1:])
                hangoutname = None
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = hangups.ui.utils.get_conv_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
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
                self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
    
            elif command == 'disconnect':
                message = '@%s: ' % msg.username
                if not len(args):
                    message += u'sorry, but you have to specify a Hangout Id for command `disconnect`'
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return
    
                hangoutid = args[0]
                hangoutname = None
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = hangups.ui.utils.get_conv_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
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
                self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
    
            elif command == 'setsyncjoinmsgs':
                message = '@%s: ' % msg.username
                if len(args) != 2:
                    message += u'sorry, but you have to specify a Hangout Id and a `true` or `false` for command `setsyncjoinmsgs`'
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return
    
                hangoutid = args[0]
                enable = args[1]
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = hangups.ui.utils.get_conv_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return
    
                if msg.channel.startswith('D'):
                    channelname = 'DM'
                else:
                    channelname = '#%s' % self.get_channelname(msg.channel)
    
                if enable.lower() in [ 'true', 'on', 'y', 'yes' ]:
                    enable = True
                elif enable.lower() in [ 'false', 'off', 'n', 'no' ]:
                    enable = False
                else:
                    message += u'sorry, but "%s" is not "true" or "false"' % enable
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return
    
                try:
                    self.setsyncjoinmsgs(msg.channel, hangoutid, enable)
                except NotSyncingError:
                    message += u'This channel (%s) is not synced with Hangout _%s_, not changing syncjoinmsgs.' % (channelname, hangoutname)
                else:
                    message += u'OK, I will %s sync join/leave messages in this channel (%s) with Hangout _%s_.' % (('now' if enable else 'no longer'), channelname, hangoutname)
                self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
    
            elif command == 'sethotag':
                message = '@%s: ' % msg.username
                if len(args) < 2:
                    message += u'sorry, but you have to specify a Hangout Id and a tag (or "none") for command `sethotag`'
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return
    
                hangoutid = args[0]
                hotag = ' '.join(args[1:])
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = hangups.ui.utils.get_conv_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
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
                self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
    
            elif command == 'setimageupload':
                message = '@%s: ' % msg.username
                if len(args) != 2:
                    message += u'sorry, but you have to specify a Hangout Id and a `true` or `false` for command `setimageupload`'
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return
    
                hangoutid = args[0]
                upload = args[1]
                for c in self.bot.list_conversations():
                    if c.id_ == hangoutid:
                        hangoutname = hangups.ui.utils.get_conv_name(c, truncate=False)
                        break
                if not hangoutname:
                    message += u'sorry, but I\'m not a member of a Hangout with Id %s' % hangoutid
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return
    
                if msg.channel.startswith('D'):
                    channelname = 'DM'
                else:
                    channelname = '#%s' % self.get_channelname(msg.channel)
    
                if upload.lower() in [ 'true', 'on', 'y', 'yes' ]:
                    upload = True
                elif upload.lower() in [ 'false', 'off', 'n', 'no' ]:
                    upload = False
                else:
                    message += u'sorry, but "%s" is not "true" or "false"' % upload
                    self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)
                    return
    
                try:
                    self.setimageupload(msg.channel, hangoutid, upload)
                except NotSyncingError:
                    message += u'This channel (%s) is not synced with Hangout _%s_, not changing imageupload.' % (channelname, hangoutname)
                else:
                    message += u'OK, I will %s upload images shared in this channel (%s) with Hangout _%s_.' % (('now' if upload else 'no longer'), channelname, hangoutname)
                self.slack.api_call('chat.postMessage', channel=msg.channel, text=message, as_user=True, link_names=True)

    def syncto(self, channel, hangoutid, shortname):
        for sync in self.syncs:
            if sync.channelid == channel and sync.hangoutid == hangoutid:
                raise AlreadySyncingError

        sync = SlackRTMSync(channel, hangoutid, shortname)
        print('slackrtm: adding sync=%s' % sync.toDict())
        self.syncs.append(sync)
        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        print('slackrtm: storing sync=%s' % sync.toDict())
        syncs.append( sync.toDict() )
        self.bot.user_memory_set(self.name, 'synced_conversations', syncs)
        return

    def disconnect(self, channel, hangoutid):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
                print('slackrtm: removing running sync=%s' % s)
                self.syncs.remove(s)
        if not sync:
            raise NotSyncingError

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                print('slackrtm: removing stored sync=%s' % s)
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

        print('slackrtm: setting sync_joins=%s for sync=%s' % (enable, sync.toDict()))
        sync.sync_joins = enable

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        print('slackrtm: storing new sync=%s with changed sync_joins' % s)
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

        print('slackrtm: setting hotag="%s" for sync=%s' % (hotag, sync.toDict()))
        sync.hotag = hotag

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        print('slackrtm: storing new sync=%s with changed hotag' % s)
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

        print('slackrtm: setting image_upload=%s for sync=%s' % (upload, sync.toDict()))
        sync.image_upload = upload

        syncs = self.bot.user_memory_get(self.name, 'synced_conversations')
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        print('slackrtm: storing new sync=%s with changed hotag' % s)
        syncs.append(sync.toDict())
        self.bot.user_memory_set(self.name, 'synced_conversations', syncs)
        return

    def handle_reply(self, reply):
        try:
            msg = SlackMessage(self, reply)
            response = u'<b>%s%s:</b> %s' % (msg.username4ho, msg.edited, self.textToHtml(msg.text))
        except ParseError as e:
            return
        except Exception as e:
            print('slackrtm: unexpected Exception while parsing slack reply: %s(%s)' % (type(e), str(e)))
            return

        try:
            self.handleCommands(msg)
        except Exception as e:
            print('slackrtm: exception while handleCommands(): %s(%s)' % (type(e), str(e)))
            traceback.print_exc()

        for sync in self.get_syncs(channelid = msg.channel):
            if not sync.sync_joins and msg.is_joinleave:
                continue
            if not msg.from_ho_id == sync.hangoutid:
                print('slackrtm: forwarding to HO %s: %s' % (sync.hangoutid, response.encode('utf-8')))
                if msg.file_attachment:
                    if sync.image_upload:
                        self.loop.call_soon_threadsafe(asyncio.async, self.upload_image(sync.hangoutid, msg.file_attachment))
                    else:
                        # we should not upload the images, so we have to send the url instead
                        response += msg.file_attachment
                self.bot.send_html_to_conversation(sync.hangoutid, response)

    def handle_ho_message(self, event):
        for sync in self.get_syncs(hangoutid = event.conv_id):
            fullname = event.user.full_name
            if sync.hotag:
                fullname = '%s (%s)' % (fullname, sync.hotag)
            try:
                photo_url = "http:"+self.bot._user_list.get_user(event.user_id).photo_url
            except Exception as e:
                print('slackrtm: exception while getting user from bot: %s' % e)
                photo_url = ''
#            # a file shared in HO is a message containing *only* the url to it
#            if re.match(r'^https?://[^ /]*googleusercontent.com/[^ ]*$', event.text, re.IGNORECASE):
#                print('slackrtm: found image: %s' % event.text)
#                image_link = event.text
#                try:
#                    filename = os.path.basename(image_link)
#                    image_response = urllib.request.urlretrieve(image_link, filename)
#                    #data = image_response.read()
#                    #print('slackrtm: data="%s"' % str(data))
#                    slacker_client = slacker.Slacker(self.apikey)
#                    response = slacker_client.files.upload(filename,
#                                                           channels=sync.channelid)
#                except Exception as e:
#                    print('slackrtm: exception while loading image: %s(%s)' % (e, str(e)))
#            else:
#                print('slackrtm: NO image in message: "%s"' % event.text)
            message = chatMessageEvent2SlackText(event.conv_event)
            message = u'%s <ho://%s/%s| >' % (message, event.conv_id, event.user_id.chat_id)
            print("slackrtm: Sending to channel %s: %s" % (sync.channelid, message.encode('utf-8')))
            self.slack.api_call('chat.postMessage',
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
    
        for sync in self.get_syncs(hangoutid = event.conv_id):
            if not sync.sync_joins:
                continue
            if sync.hotag:
                honame = sync.hotag
            else:
                honame = hangups.ui.utils.get_conv_name(event.conv)
            # JOIN
            if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
                invitee = u'<https://plus.google.com/%s/about|%s>' % (event.user_id.chat_id, event.user.full_name)
                message = u'%s has added %s to _%s_' % (invitee, names, honame)
            # LEAVE
            else:
                message = u'%s has left _%s_' % (names, honame)
            message = unicodeemoji2text(message)
            message = u'%s <ho://%s/%s| >' % (message, event.conv_id, event.user_id.chat_id)
            print("slackrtm: Sending to channel/group %s: %s" % (sync.channelid, message))
            self.slack.api_call('chat.postMessage',
                                channel=sync.channelid,
                                text=message,
                                as_user=True,
                                link_names=True)

    def handle_ho_rename(self, event):
        name = hangups.ui.utils.get_conv_name(event.conv, truncate=False)
    
        for sync in self.get_syncs(hangoutid = event.conv_id):
            invitee = u'<https://plus.google.com/%s/about|%s>' % (event.user_id.chat_id, event.user.full_name)
            hotagaddendum = ''
            if sync.hotag:
                hotagaddendum = ' _%s_' % sync.hotag
            message = u'%s has renamed the Hangout%s to _%s_' % (invitee, hotagaddendum, name)
            message = unicodeemoji2text(message)
            message = u'%s <ho://%s/%s| >' % (message, event.conv_id, event.user_id.chat_id)
            print("slackrtm: Sending to channel/group %s: %s" % (sync.channelid, message))
            self.slack.api_call('chat.postMessage',
                                channel=sync.channelid,
                                text=message,
                                as_user=True,
                                link_names=True)


slackrtms = []
class SlackRTMThread(threading.Thread):
    def __init__(self, bot, loop, config):
        super(SlackRTMThread, self).__init__()
        self._stop = threading.Event()
        self._bot = bot
        self._loop = loop
        self._config = config
        self._listener = None

    def run(self):
        print('slackrtm: SlackRTMThread.run()')
        asyncio.set_event_loop(self._loop)
        global slackrtms

        try:
            if self._listener:
                slackrtms.remove(self._listener)
            self._listener = SlackRTM(self._config, self._bot, self._loop, threaded=True)
            slackrtms.append(self._listener)
            last_ping = int(time.time())
            while True:
                if self.stopped():
                    return
                replies = self._listener.rtm_read()
                if replies:
                    if 'type' in replies[0]:
                        if replies[0]['type'] == 'hello':
                            #print('slackrtm: ignoring first replies including type=hello message to avoid message duplication: %s...' % str(replies)[:30])
                            continue
                    for reply in replies:
                        try:
                            self._listener.handle_reply(reply)
                        except Exception as e:
                            print('slackrtm: unhandled exception during handle_reply(): %s\n%s' % (str(e), pprint.pformat(reply)))
                            traceback.print_exc()
                now = int(time.time())
                if now > last_ping + 30:
                    self._listener.ping()
                    last_ping = now
                time.sleep(.1)
        except KeyboardInterrupt:
            # close, nothing to do
            return
        except WebSocketConnectionClosedException as e:
            print('slackrtm: SlackRTMThread: got WebSocketConnectionClosedException("%s")' % str(e))
            return self.run()
        except IncompleteLoginError:
            print('slackrtm: SlackRTMThread: got IncompleteLoginError, restarting')
            time.sleep(1)
            return self.run()
        except ConnectionFailedError:
            print('slackrtm: SlackRTMThread: got ConnectionFailedError, waiting 10 sec trying to restart')
            time.sleep(10)
            return self.run()
        except Exception as e:
            print('slackrtm: SlackRTMThread: unhandled exception: %s' % str(e))
            traceback.print_exc()
        return

    def stop(self):
        global slackrtms
        if self._listener:
            slackrtms.remove(self._listener)
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()


def _initialise(Handlers, bot=None):
    print('slackrtm: _initialise()')

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
    logging.info(_("_start_slackrtm_sinks(): %d sink thread(s) started" % len(threads)))

    Handlers.register_handler(_handle_slackout)
    Handlers.register_handler(_handle_membership_change, type="membership")
    Handlers.register_handler(_handle_rename, type="rename")

    Handlers.register_admin_command(["slacks", "slack_channels", "slack_listsyncs", "slack_syncto", "slack_disconnect", "slack_setsyncjoinmsgs", "slack_setimageupload", "slack_sethotag"])
    return []

@asyncio.coroutine
def _handle_slackout(bot, event, command):
    if not slackrtms:
        return
    for slackrtm in slackrtms:
        try:
            slackrtm.handle_ho_message(event)
        except Exception as e:
            print('slackrtm: _handle_slackout threw: %s' % str(e))
            traceback.print_exc()

@asyncio.coroutine
def _handle_membership_change(bot, event, command):
    if not slackrtms:
        return
    for slackrtm in slackrtms:
        try:
            slackrtm.handle_ho_membership(event)
        except Exception as e:
            print('slackrtm: _handle_membership_change threw: %s' % str(e))
            traceback.print_exc()


@asyncio.coroutine
def _handle_rename(bot, event, command):
    if not slackrtms:
        return
    for slackrtm in slackrtms:
        try:
            slackrtm.handle_ho_rename(event)
        except Exception as e:
            print('slackrtm: _handle_rename threw: %s' % str(e))
            traceback.print_exc()

# /bot slacks _lists all configured slack teams_
# /bot slack_channels TEAMNAME _lists all channels/groups of slack team TEAMNAME_
# /bot slack_syncto TEAMNAME CHANNELIID [Hangout-Tag] _starts syncing of messages between current Hangout and channel CHANNELID in slack team TEAMNAME, if given, all messages from Hangouts will be tagged with Hangout-Tag in Slack_
# /bot slack_disconnect TEAMNAME CHANNELID _stops sync of current Hangout with channel CHANNELID in slack team TEAMNAME_

def slacks(bot, event, *args):
    """list all slacks configured"""
    segments = [
        hangups.ChatMessageSegment('Slack configured:', is_bold=True),
        hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
        ]
    for slackrtm in slackrtms:
        segments.append(hangups.ChatMessageSegment('%s' % slackrtm.name))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    bot.send_message_segments(event.conv, segments)

def slack_channels(bot, event, *args):
    """list all slack channels available in given slack team"""
    if len(args) != 1:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name to list channels of', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in slackrtms:
        if s.name == slackname:
            slackrtm = s
            break
    if not slackrtm:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: Could not find a configured slack team with name "%s", use /bot slacks to list all teams' % slackname, is_bold=True)])
        return

    segments = [
        hangups.ChatMessageSegment('Slack channels in team %s:' % (slackname), is_bold=True),
        hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
        ]
    slackrtm.update_channelnames()
    for id in slackrtm.channelnames:
        segments.append(hangups.ChatMessageSegment('%s (%s)' % (slackrtm.channelnames[id], id)))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    segments.append(hangups.ChatMessageSegment('private groups:', is_bold=True))
    segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    slackrtm.update_groupnames()
    for id in slackrtm.groupnames:
        segments.append(hangups.ChatMessageSegment('%s (%s)' % (slackrtm.groupnames[id], id)))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
                
    bot.send_message_segments(event.conv, segments)

def slack_listsyncs(bot, event, *args):
    segments = [ 
        hangups.ChatMessageSegment('list of current sync connections:', is_bold=True),
        hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)
        ]
    for slackrtm in slackrtms:
        for sync in slackrtm.syncs:
            hangoutname = 'unknown'
            for c in bot.list_conversations():
                if c.id_ == sync.hangoutid:
                    hangoutname = hangups.ui.utils.get_conv_name(c, truncate=False)
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
    """connects current hangout with given slack channel in given slack team"""
    if len(args) >= 3:
        honame = ' '.join(args[2:])
    else:
        if len(args) != 2:
            bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name and a channel', is_bold=True)])
            return
        honame = hangups.ui.utils.get_conv_name(event.conv)

    slackname = args[0]
    slackrtm = None
    for s in slackrtms:
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
    """stops syncing current hangout with given slack channel in given slack team"""
    if len(args) != 2:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name and a channel', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in slackrtms:
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
    """enable/disable messages about joins/leaves/adds/invites/kicks when syncing current hangout with given slack channel in given slack team, default is enabled"""
    if len(args) != 3:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name, a channel and "true" or "false"', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in slackrtms:
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
    if enable.lower() in [ 'true', 'on', 'y', 'yes' ]:
        enable = True
    elif enable.lower() in [ 'false', 'off', 'n', 'no' ]:
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
    """enable/disable image uplad to current hangout when shared in given slack channel in given slack team, default is enabled"""
    if len(args) != 3:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name, a channel and "true" or "false"', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in slackrtms:
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
    if upload.lower() in [ 'true', 'on', 'y', 'yes' ]:
        upload = True
    elif upload.lower() in [ 'false', 'off', 'n', 'no' ]:
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
    """set the tag of current hangout when syncing messages to the given slack channel in given slack team, default is the name of the Hangout when sync was set up, use 'none' to disable tagging"""
    if len(args) < 3:
        bot.send_message_segments(event.conv, [hangups.ChatMessageSegment('ERROR: You must specify a slack team name, a channel and a tag', is_bold=True)])
        return

    slackname = args[0]
    slackrtm = None
    for s in slackrtms:
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
