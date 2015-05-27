import time
import re
import os
import pprint
import traceback

import threading
import hangups.ui.utils
from slackclient import SlackClient
from websocket import WebSocketConnectionClosedException

import asyncio
import logging
import hangups
import json

import emoji
import urllib
import slacker

""" SlackRTM plugin for listening to hangouts and slack and syncing messages between the two.
config.json will have to be configured as follows:
"slackrtm": [{
  "name": "SlackNameForLoggingEtc",
  "key": "SLACK_API_KEY",
  "synced_conversations": [
  ["SLACK_CHANNEL_ID1", "CONV_ID1", "optHONameForSenderDisplay"],
  ["SLACK_CHANNEL_ID1", "CONV_ID1", "optHONameForSenderDisplay"]
  ]
}]

You can (theoretically) set up as many slack sinks per bot as you like, by extending the list"""


def unicodeemoji2text(text):
    out = u''
    for c in text[:]:
        try:
            c = emoji.decode(c)
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

class SlackMessage(object):
    def __init__(self, slackrtm, reply):
        self.text = None
        self.username = None
        self.edited = None
        self.from_ho_id = None
        self.sender_id = None
        self.channel = None
        self.file_attachment = None

        if not 'type' in reply:
            print("slackrtm: No 'type' in reply:")
            print("slackrtm: "+str(reply))
            raise ParseError('No "type" in reply:\n%s' % str(reply))
    
        if reply['type'] in ['pong', 'presence_change',  'user_typing', 'file_shared', 'file_public', 'file_comment_added', 'file_comment_deleted']:
            # we ignore pong's as they are only answers for our pings
            raise ParseError('Not a "message" type reply: type=%s' % reply['type'])

        text = u''
        username = ''
        edited = ''
        from_ho_id = ''
        sender_id = ''
        channel = None
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

        if not is_bot:
            username = u'%s (Slack)' % slackrtm.get_username(user, user)
        elif sender_id != '':
            username = u'<a href="https://plus.google.com/%s">%s</a>' % (sender_id, username)

        if 'channel' in reply:
            channel = reply['channel']
        elif 'group' in reply:
            channel = reply['group']
        if not channel:
            print('slackrtm: no channel or group in reply: %s' % pprint.pformat(reply))
            raise ParseError('no channel found in reply:\n%s' % str(reply))

        self.text = text
        self.username = username
        self.edited = edited
        self.from_ho_id = from_ho_id
        self.sender_id = sender_id
        self.channel = channel
        self.file_attachment = file_attachment


class SlackRTM(object):
    def __init__(self, sink_config, bot, threaded=False):
        self.bot = bot
        self.config = sink_config
        self.apikey = self.config['key']
        self.threadname = None

        self.slack = SlackClient(self.apikey)
        self.slack.rtm_connect()
        if threaded:
            if 'name' in self.config:
                name = self.config['name']
            else:
                name = '%s@%s' % (self.slack.server.login_data['self']['name'], self.slack.server.login_data['team']['domain'])
            self.threadname = 'SlackRTM:' + name
            threading.current_thread().name = self.threadname
            print('slackrtm: Started RTM connection for SlackRTM thread %s' % pprint.pformat(threading.current_thread()))
            for t in threading.enumerate():
                if t.name == self.threadname and t != threading.current_thread():
                    print("slackrtm: Old thread found - killing")
                    t.stop()


        self.update_usernames(self.slack.server.login_data['users'])
        self.update_channelnames(self.slack.server.login_data['channels'])
        self.my_uid = self.slack.server.login_data['self']['id']

        self.hangoutids = {}
        self.hangoutnames = {}
        for c in self.bot.list_conversations():
            name = hangups.ui.utils.get_conv_name(c, truncate=True)
            self.hangoutids[ name ] = c.id_
            self.hangoutnames[ c.id_ ] = name

        self.hosinks = {}
        self.slacksinks = {}
        for conv in self.config["synced_conversations"]:
            honame = ''
            if len(conv) == 3:
                honame = conv[2]
            else:
                if not conv[1] in self.hangoutnames:
                    print("slackrtm: could not find conv %s in bot's conversations!" % conv[1])
                    honame = conv[1]
                else:
                    honame = self.hangoutnames[ conv[1] ]
            if not conv[0] in self.hosinks:
                self.hosinks[ conv[0] ] = []
            self.hosinks[ conv[0] ].append( (conv[1], honame) )
            if not conv[1] in self.slacksinks:
                self.slacksinks[ conv[1] ] = []
            self.slacksinks[ conv[1] ].append( (conv[0], honame) )

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
        text = emoji.emojize(text)
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

    def handle_reply(self, reply):
        try:
            msg = SlackMessage(self, reply)
            response = u'<b>%s%s:</b> %s' % (msg.username, msg.edited, self.textToHtml(msg.text))
        except ParseError as e:
            return
        except Exception as e:
            print('slackrtm: unexpected Exception while parsing slack reply: %s(%s)' % (type(e), str(e)))
            return


        if msg.text.startswith('<@%s> whereami' % self.my_uid) or \
                msg.text.startswith('<@%s>: whereami' % self.my_uid):
            message = u'@%s: you are in channel %s' % (msg.username, msg.channel)
            self.slack.api_call('chat.postMessage',
                                channel=msg.channel,
                                text=msg.message,
                                as_user=True,
                                link_names=True)

        for hoid, honame in self.hosinks.get(msg.channel, []):
            if msg.from_ho_id == hoid:
                print('slackrtm: NOT forwarding to HO %s: %s' % (hoid, response))
            else:
                print('slackrtm:     forwarding to HO %s: %s' % (hoid, response))
                if msg.file_attachment:
                    loop = asyncio.get_event_loop()
                    loop.call_soon_threadsafe(asyncio.async, self.upload_image(hoid, msg.file_attachment))
#                for userchatid in self.bot.memory.get_option("user_data"):
#                    userslackrtmtest = self.bot.memory.get_suboption("user_data", userchatid, "slackrtmtest")
#                    if userslackrtmtest:
#                        print('slackrtm: memory-test: %s => %s' % (userchatid, userslackrtmtest))
                if not self.bot.send_html_to_user(hoid, response):
                    self.bot.send_html_to_conversation(hoid, response)

    def handle_ho_message(self, event):
        for channel_id, honame in self.slacksinks.get(event.conv_id, []):
            fullname = '%s (%s)' % (event.user.full_name, honame)
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
#                                                           channels=channel_id)
#                except Exception as e:
#                    print('slackrtm: exception while loading image: %s(%s)' % (e, str(e)))
#            else:
#                print('slackrtm: NO image in message: "%s"' % event.text)
            message = chatMessageEvent2SlackText(event.conv_event)
            message = u'%s <ho://%s/%s| >' % (message, event.conv_id, event.user_id.chat_id)
            print("slackrtm: Sending to channel %s: %s" % (channel_id, message.encode('utf-8')))
#            self.bot.user_memory_set(event.user.id_.chat_id, 'slackrtmtest', event.text)
            self.slack.api_call('chat.postMessage',
                                channel=channel_id,
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
    
        for channel_id, honame in self.slacksinks.get(event.conv_id, []):
            # JOIN
            if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
                invitee = u'<https://plus.google.com/%s/about|%s>' % (event.user_id.chat_id, event.user.full_name)
                message = u'%s has added %s to _%s_' % (invitee, names, honame)
            # LEAVE
            else:
                message = u'%s has left _%s_' % (names, honame)
            message = unicodeemoji2text(message)
            message = u'%s <ho://%s/%s| >' % (message, event.conv_id, event.user_id.chat_id)
            print("slackrtm: Sending to channel/group %s: %s" % (channel_id, message))
            self.slack.api_call('chat.postMessage',
                                channel=channel_id,
                                text=message,
                                as_user=True,
                                link_names=True)

    def handle_ho_rename(self, event):
        name = hangups.ui.utils.get_conv_name(event.conv, truncate=False)
    
        for channel_id, honame in self.slacksinks.get(event.conv_id, []):
            invitee = u'<https://plus.google.com/%s/about|%s>' % (event.user_id.chat_id, event.user.full_name)
            message = u'%s has renamed the Hangout _%s_ to _%s_' % (invitee, honame, name)
            message = unicodeemoji2text(message)
            message = u'%s <ho://%s/%s| >' % (message, event.conv_id, event.user_id.chat_id)
            print("slackrtm: Sending to channel/group %s: %s" % (channel_id, message))
            self.slack.api_call('chat.postMessage',
                                channel=channel_id,
                                text=message,
                                as_user=True,
                                link_names=True)


def _initialise(Handlers, bot=None):
    print('slackrtm: _initialise()')
    if bot:
        _start_slackrtm_sinks(bot)
    else:
        print("slackrtm: Slack sinks could not be initialized.")
    Handlers.register_handler(_handle_slackout)
    Handlers.register_handler(_handle_membership_change, type="membership")
    Handlers.register_handler(_handle_rename, type="rename")
    return []


def _start_slackrtm_sinks(bot):
    print('slackrtm: _start_slackrtm_sinks()')
    # Start and asyncio event loop
    loop = asyncio.get_event_loop()

    slack_sink = bot.get_config_option('slackrtm')
    if not isinstance(slack_sink, list):
        return

    threads = []
    for sinkConfig in slack_sink:
        # start up slack listener in a separate thread
        t = SlackRTMThread(bot, loop, sinkConfig)
        t.daemon = True
        t.start()
        threads.append(t)
    logging.info(_("_start_slackrtm_sinks(): %d sink thread(s) started" % len(threads)))

slackrtms = []
class SlackRTMThread(threading.Thread):
    def __init__(self, bot, loop, config):
        super(SlackRTMThread, self).__init__()
        self._stop = threading.Event()
        self._bot = bot
        self._loop = loop
        self._config = config

    def run(self):
        print('slackrtm: SlackRTMThread starts listening')
        asyncio.set_event_loop(self._loop)
        global slackrtms

        try:
            listener = SlackRTM(self._config, self._bot, threaded=True)
            slackrtms.append(listener)
            last_ping = int(time.time())
            while True:
                if self.stopped():
                    return
                replies = listener.rtm_read()
                if replies:
                    if 'type' in replies[0]:
                        if replies[0]['type'] == 'hello':
                            #print('slackrtm: ignoring first replies including type=hello message to avoid message duplication: %s...' % str(replies)[:30])
                            continue
                    for reply in replies:
                        try:
                            listener.handle_reply(reply)
                        except Exception as e:
                            print('slackrtm: unhandled exception during handle_reply(): %s\n%s' % (str(e), pprint.pformat(reply)))
                            traceback.print_exc()
                now = int(time.time())
                if now > last_ping + 30:
                    listener.ping()
                    last_ping = now
                time.sleep(1)
        except KeyboardInterrupt:
            # close, nothing to do
            return
        except WebSocketConnectionClosedException as e:
            print('slackrtm: SlackRTMThread: got WebSocketConnectionClosedException("%s")' % str(e))
            return self.run()
        except Exception as e:
            print('slackrtm: SlackRTMThread: unhandled exception: %s' % str(e))
            traceback.print_exc()
        return

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()

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
