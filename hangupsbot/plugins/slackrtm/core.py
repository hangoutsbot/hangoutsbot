import asyncio
import json
import html
import logging
import mimetypes
import os
import pprint
import re
import threading
import time
import urllib.request
import hangups
import emoji

import hangups_shim as hangups

from slackclient import SlackClient
from websocket import WebSocketConnectionClosedException

from .bridgeinstance import ( BridgeInstance,
                              FakeEvent )
from .commands_slack import slackCommandHandler
from .exceptions import ( AlreadySyncingError,
                          ConnectionFailedError,
                          NotSyncingError,
                          ParseError,
                          IncompleteLoginError )
from .parsers import ( slack_markdown_to_hangups,
                       hangups_markdown_to_slack )
from .utils import  ( _slackrtms,
                      _slackrtm_conversations_set,
                      _slackrtm_conversations_get )


logger = logging.getLogger(__name__)


# fix for simple_smile support
emoji.EMOJI_UNICODE[':simple_smile:'] = emoji.EMOJI_UNICODE[':smiling_face:']
emoji.EMOJI_ALIAS_UNICODE[':simple_smile:'] = emoji.EMOJI_UNICODE[':smiling_face:']


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

        if reply['type'] in [ 'pong', 'presence_change', 'user_typing', 'file_shared', 'file_public',
                              'file_comment_added', 'file_comment_deleted', 'message_deleted', 'file_created' ]:

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
                # dev: normal messages that are entered by a slack user usually go this route
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

        """
        strip :skin-tone-<id>: if present and apparently combined with an actual emoji alias
        * depends on the slack users emoji style, e.g. hangouts style has no skin tone support
        * do it BEFORE emojize() for more reliable detection of sub-pattern :some_emoji(::skin-tone-\d:)
        """
        text = re.sub(r"::skin-tone-\d:", ":", text, flags=re.IGNORECASE)

        # convert emoji aliases into their unicode counterparts
        text = emoji.emojize(text, use_aliases=True)

        username4ho = username
        realname4ho = username
        tag_from_slack = False # XXX: prevents key not defined on unmonitored channels
        if not is_bot:
            domain = slackrtm.get_slack_domain()
            username = slackrtm.get_username(user, user)
            realname = slackrtm.get_realname(user,username)

            username4ho = u'{2}'.format(domain, username, username)
            realname4ho = u'{2}'.format(domain, username, realname)
            tag_from_slack = True
        elif sender_id != '':
            username4ho = u'{1}'.format(sender_id, username)
            realname4ho = u'{1}'.format(sender_id, username)
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
    def __init__(self, hangoutsbot, channelid, hangoutid, hotag, slacktag, sync_joins=True, image_upload=True, showslackrealnames=False, showhorealnames="real"):
        self.channelid = channelid
        self.hangoutid = hangoutid
        self.hotag = hotag
        self.sync_joins = sync_joins
        self.image_upload = image_upload
        self.slacktag = slacktag
        self.showslackrealnames = showslackrealnames
        self.showhorealnames = showhorealnames

        handler_metadata = {}
        handler_metadata.update({ "module": "slackrtm", "module.path": "plugins.slackrtm" }) # required: late-registration
        handler_metadata.update({ "channel": channelid, "hangouts":  hangoutid }) # example: extra identification
        self._bridgeinstance = BridgeInstance(hangoutsbot, "slackrtm", extra_metadata = handler_metadata)

        self._bridgeinstance.set_extra_configuration(hangoutid, channelid)

    @staticmethod
    def fromDict(hangoutsbot, sync_dict):
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
        slackrealnames = True
        if 'showslackrealnames' in sync_dict and not sync_dict['showslackrealnames']:
            slackrealnames = False
        horealnames = 'real'
        if 'showhorealnames' in sync_dict:
            horealnames = sync_dict['showhorealnames']
        return SlackRTMSync( hangoutsbot,
                             sync_dict['channelid'],
                             sync_dict['hangoutid'],
                             sync_dict['hotag'],
                             slacktag,
                             sync_joins,
                             image_upload,
                             slackrealnames,
                             horealnames)

    def toDict(self):
        return {
            'channelid': self.channelid,
            'hangoutid': self.hangoutid,
            'hotag': self.hotag,
            'sync_joins': self.sync_joins,
            'image_upload': self.image_upload,
            'slacktag': self.slacktag,
            'showslackrealnames': self.showslackrealnames,
            'showhorealnames': self.showhorealnames,
            }

    def getPrintableOptions(self):
        return 'hotag=%s, sync_joins=%s, image_upload=%s, slacktag=%s, showslackrealnames=%s, showhorealnames="%s"' % (
            '"{}"'.format(self.hotag) if self.hotag else 'NONE',
            self.sync_joins,
            self.image_upload,
            '"{}"'.format(self.slacktag) if self.slacktag else 'NONE',
            self.showslackrealnames,
            self.showhorealnames,
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
        syncs = _slackrtm_conversations_get(self.bot, self.name)
        if not syncs:
            syncs = []

        for s in syncs:
            sync = SlackRTMSync.fromDict(self.bot, s)
            if sync.slacktag == 'NOT_IN_CONFIG':
                sync.slacktag = self.get_teamname()
            sync.team_name = self.name # chatbridge needs this for context
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
                _new_sync = SlackRTMSync(self.bot, conv[0], conv[1], hotag, self.get_teamname())
                _new_sync.team_name = self.name # chatbridge needs this for context
                self.syncs.append(_new_sync)

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

    def get_channelgroupname(self, channel, default=None):
        if channel.startswith('C'):
            return self.get_channelname(channel, default)
        if channel.startswith('G'):
            return self.get_groupname(channel, default)
        if channel.startswith('D'):
            return 'DM'
        return default

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
                out = "#%s" % self.get_channelgroupname(match.group(3),
                                                        'unknown:%s' % match.group(3))
        else:
            linktarget = match.group(1)
            if linktext == "":
                linktext = linktarget
            out = '[{}]({})'.format(linktext, linktarget)
        out = out.replace('_', '%5F')
        out = out.replace('*', '%2A')
        out = out.replace('`', '%60')
        return out

    @asyncio.coroutine
    def upload_image(self, image_uri, sync, username, userid, channel_name):
        token = self.apikey
        logger.info('downloading %s', image_uri)
        filename = os.path.basename(image_uri)
        request = urllib.request.Request(image_uri)
        request.add_header("Authorization", "Bearer %s" % token)
        image_response = urllib.request.urlopen(request)
        content_type = image_response.info().get_content_type()

        filename_extension = mimetypes.guess_extension(content_type).lower() # returns with "."
        physical_extension = "." + filename.rsplit(".", 1).pop().lower()

        if physical_extension == filename_extension:
            pass
        elif filename_extension == ".jpe" and physical_extension in [ ".jpg", ".jpeg", ".jpe", ".jif", ".jfif" ]:
            # account for mimetypes idiosyncrancy to return jpe for valid jpeg
            pass
        else:
            logger.warning("unable to determine extension: {} {}".format(filename_extension, physical_extension))
            filename += filename_extension

        logger.info('uploading as %s', filename)
        image_id = yield from self.bot._client.upload_image(image_response, filename=filename)

        logger.info('sending HO message, image_id: %s', image_id)
        yield from sync._bridgeinstance._send_to_internal_chat(
            sync.hangoutid,
            "shared media from slack",
            {   "sync": sync,
                "source_user": username,
                "source_uid": userid,
                "source_title": channel_name },
            image_id=image_id )

    def config_syncto(self, channel, hangoutid, shortname):
        for sync in self.syncs:
            if sync.channelid == channel and sync.hangoutid == hangoutid:
                raise AlreadySyncingError

        sync = SlackRTMSync(self.bot, channel, hangoutid, shortname, self.get_teamname())
        sync.team_name = self.name # chatbridge needs this for context
        logger.info('adding sync: %s', sync.toDict())
        self.syncs.append(sync)
        syncs = _slackrtm_conversations_get(self.bot, self.name)
        if not syncs:
            syncs = []
        logger.info('storing sync: %s', sync.toDict())
        syncs.append(sync.toDict())
        _slackrtm_conversations_set(self.bot, self.name, syncs)
        return

    def config_disconnect(self, channel, hangoutid):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
                logger.info('removing running sync: %s', s)
                s._bridgeinstance.close()
                self.syncs.remove(s)
        if not sync:
            raise NotSyncingError

        syncs = _slackrtm_conversations_get(self.bot, self.name)
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                logger.info('removing stored sync: %s', s)
                syncs.remove(s)
        _slackrtm_conversations_set(self.bot, self.name, syncs)
        return

    def config_setsyncjoinmsgs(self, channel, hangoutid, enable):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting sync_joins=%s for sync=%s', enable, sync.toDict())
        sync.sync_joins = enable

        syncs = _slackrtm_conversations_get(self.bot, self.name)
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed sync_joins', s)
        syncs.append(sync.toDict())
        _slackrtm_conversations_set(self.bot, self.name, syncs)
        return

    def config_sethotag(self, channel, hangoutid, hotag):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting hotag="%s" for sync=%s', hotag, sync.toDict())
        sync.hotag = hotag

        syncs = _slackrtm_conversations_get(self.bot, self.name)
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed hotag', s)
        syncs.append(sync.toDict())
        _slackrtm_conversations_set(self.bot, self.name, syncs)
        return

    def config_setimageupload(self, channel, hangoutid, upload):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting image_upload=%s for sync=%s', upload, sync.toDict())
        sync.image_upload = upload

        syncs = _slackrtm_conversations_get(self.bot, self.name)
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed hotag', s)
        syncs.append(sync.toDict())
        _slackrtm_conversations_set(self.bot, self.name, syncs)
        return

    def config_setslacktag(self, channel, hangoutid, slacktag):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting slacktag="%s" for sync=%s', slacktag, sync.toDict())
        sync.slacktag = slacktag

        syncs = _slackrtm_conversations_get(self.bot, self.name)
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed slacktag', s)
        syncs.append(sync.toDict())
        _slackrtm_conversations_set(self.bot, self.name, syncs)
        return

    def config_showslackrealnames(self, channel, hangoutid, realnames):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting showslackrealnames=%s for sync=%s', realnames, sync.toDict())
        sync.showslackrealnames = realnames

        syncs = _slackrtm_conversations_get(self.bot, self.name)
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed hotag', s)
        syncs.append(sync.toDict())
        _slackrtm_conversations_set(self.bot, self.name, syncs)
        return

    def config_showhorealnames(self, channel, hangoutid, realnames):
        sync = None
        for s in self.syncs:
            if s.channelid == channel and s.hangoutid == hangoutid:
                sync = s
        if not sync:
            raise NotSyncingError

        logger.info('setting showhorealnames=%s for sync=%s', realnames, sync.toDict())
        sync.showhorealnames = realnames

        syncs = _slackrtm_conversations_get(self.bot, self.name)
        if not syncs:
            syncs = []
        for s in syncs:
            if s['channelid'] == channel and s['hangoutid'] == hangoutid:
                syncs.remove(s)
        logger.info('storing new sync=%s with changed hotag', s)
        syncs.append(sync.toDict())
        _slackrtm_conversations_set(self.bot, self.name, syncs)
        return

    def handle_reply(self, reply):
        """handle incoming replies from slack"""

        try:
            msg = SlackMessage(self, reply)
        except ParseError as e:
            return
        except Exception as e:
            logger.exception('error parsing Slack reply: %s(%s)', type(e), str(e))
            return

        # commands can be processed even from unsynced channels
        try:
            slackCommandHandler(self, msg)
        except Exception as e:
            logger.exception('error in handleCommands: %s(%s)', type(e), str(e))

        syncs = self.get_syncs(channelid=msg.channel)
        if not syncs:
            # stop processing replies if no syncs are available (optimisation)
            return

        reffmt = re.compile(r'<((.)([^|>]*))((\|)([^>]*)|([^>]*))>')
        message = reffmt.sub(self.matchReference, msg.text)
        message = slack_markdown_to_hangups(message)

        for sync in syncs:
            if not sync.sync_joins and msg.is_joinleave:
                continue

            if msg.from_ho_id != sync.hangoutid:
                username = msg.realname4ho if sync.showslackrealnames else msg.username4ho
                channel_name = self.get_channelgroupname(msg.channel)

                if msg.file_attachment:
                    if sync.image_upload:

                        self.loop.call_soon_threadsafe(
                            asyncio.async,
                            self.upload_image(
                                msg.file_attachment,
                                sync,
                                username,
                                msg.user,
                                channel_name ))

                        self.lastimg = os.path.basename(msg.file_attachment)
                    else:
                        # we should not upload the images, so we have to send the url instead
                        response += msg.file_attachment

                self.loop.call_soon_threadsafe(
                    asyncio.async,
                    sync._bridgeinstance._send_to_internal_chat(
                        sync.hangoutid,
                        message,
                        {   "sync": sync,
                            "source_user": username,
                            "source_uid": msg.user,
                            "source_gid": sync.channelid,
                            "source_title": channel_name }))

    @asyncio.coroutine
    def _send_deferred_media(self, image_link, sync, full_name, link_names, photo_url, fragment):
        self.api_call('chat.postMessage',
                      channel = sync.channelid,
                      text = "{} {}".format(image_link, fragment),
                      username = full_name,
                      link_names = True,
                      icon_url = photo_url)

    @asyncio.coroutine
    def handle_ho_message(self, event, conv_id, channel_id):
        user = event.passthru["original_request"]["user"]
        message = event.passthru["original_request"]["message"]

        if not message:
            message = ""

        message = hangups_markdown_to_slack(message)

        """slackrtm uses an overengineered pseudo SlackRTMSync "structure" to contain individual 1-1 syncs
            we rely on the chatbridge to iterate through multiple syncs, and ensure we only have
            to deal with a single mapping at this level

            XXX: the mapping SHOULD BE single, but let duplicates get through"""

        active_syncs = []
        for sync in self.get_syncs(hangoutid=conv_id):
            if sync.channelid != channel_id:
                continue
            if sync.hangoutid != conv_id:
                continue
            active_syncs.append(sync)

        for sync in active_syncs:
            bridge_user = sync._bridgeinstance._get_user_details(user, { "event": event })

            extras = []
            if sync.showhorealnames == "nick":
                display_name = bridge_user["nickname"] or bridge_user["full_name"]
            else:
                display_name = bridge_user["full_name"]
                if (sync.showhorealnames == "both" and bridge_user["nickname"] and
                        not bridge_user["full_name"] == bridge_user["nickname"]):
                    extras.append(bridge_user["nickname"])

            if sync.hotag is True:
                if "chatbridge" in event.passthru and event.passthru["chatbridge"]["source_title"]:
                    chat_title = event.passthru["chatbridge"]["source_title"]
                    extras.append(chat_title)
            elif sync.hotag:
                extras.append(sync.hotag)

            if extras:
                display_name = "{} ({})".format(display_name, ", ".join(extras))

            slackrtm_fragment = "<ho://{}/{}| >".format(conv_id, bridge_user["chat_id"] or bridge_user["preferred_name"])

            """XXX: media sending:

            * if media link is already available, send it immediately
              * real events from google servers will have the medialink in event.conv_event.attachment
              * media link can also be added as part of the passthru
            * for events raised by other external chats, wait for the public link to become available
            """


            if "attachments" in event.passthru["original_request"] and event.passthru["original_request"]["attachments"]:
                # automatically prioritise incoming events with attachments available
                media_link = event.passthru["original_request"]["attachments"][0]
                logger.info("media link in original request: {}".format(media_link))

                message = "shared media: {}".format(media_link)

            elif isinstance(event, FakeEvent):
                if( "image_id" in event.passthru["original_request"]
                        and event.passthru["original_request"]["image_id"] ):
                    # without media link, create a deferred post until a public media link becomes available
                    image_id = event.passthru["original_request"]["image_id"]
                    logger.info("wait for media link: {}".format(image_id))

                    loop = asyncio.get_event_loop()
                    task = loop.create_task(
                        self.bot._handlers.image_uri_from(
                            image_id,
                            self._send_deferred_media,
                            sync,
                            display_name,
                            True,
                            bridge_user["photo_url"],
                            slackrtm_fragment ))

            elif( hasattr(event, "conv_event")
                    and hasattr(event.conv_event, "attachments")
                    and len(event.conv_event.attachments) == 1 ):
                # catch actual events with media link  but didn' go through the passthru
                media_link = event.conv_event.attachments[0]
                logger.info("media link in original event: {}".format(media_link))

                message = "shared media: {}".format(media_link)

            """standard message relay"""

            message = "{} {}".format(message, slackrtm_fragment)

            logger.info("message {}: {}".format(sync.channelid, message))
            self.api_call('chat.postMessage',
                          channel = sync.channelid,
                          text = message,
                          username = display_name,
                          link_names = True,
                          icon_url = bridge_user["photo_url"])

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

    def close(self):
        logger.debug("closing all bridge instances")
        for s in self.syncs:
            s._bridgeinstance.close()


class SlackRTMThread(threading.Thread):
    def __init__(self, bot, loop, config):
        super(SlackRTMThread, self).__init__()
        self._stop = threading.Event()
        self._bot = bot
        self._loop = loop
        self._config = config
        self._listener = None
        self.isFullyLoaded = threading.Event()

    def run(self):
        logger.debug('SlackRTMThread.run()')
        asyncio.set_event_loop(self._loop)

        start_ts = time.time()
        try:
            if self._listener and self._listener in _slackrtms:
                self._listener.close()
                _slackrtms.remove(self._listener)
            self._listener = SlackRTM(self._config, self._bot, self._loop, threaded=True)
            _slackrtms.append(self._listener)
            last_ping = int(time.time())
            self.isFullyLoaded.set()
            while True:
                if self.stopped():
                    return
                replies = self._listener.rtm_read()
                if replies:
                    for reply in replies:
                        if "type" not in reply:
                            logger.warning("no type available for {}".format(reply))
                            continue
                        if reply["type"] == "hello":
                            # discard the initial api reply
                            continue
                        if reply["type"] == "message" and float(reply["ts"]) < start_ts:
                            # discard messages in the queue older than the thread start timestamp
                            continue
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
        if self._listener and self._listener in _slackrtms:
            self._listener.close()
            _slackrtms.remove(self._listener)
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()
