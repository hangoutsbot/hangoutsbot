import time
import re
import os
import pprint

import threading
import hangups.ui.utils
from slackclient import SlackClient

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

    def handle_reply(self, reply):
        if not 'type' in reply:
            print("slackrtm: No 'type' in reply:")
            print("slackrtm: "+str(reply))
            return
    
        if reply['type'] in ['pong', 'presence_change',  'user_typing', 'file_shared', 'file_public', 'file_comment_added', 'file_comment_deleted' ]:
            # we ignore pong's as they are only answers for our pings
            return
    
        user = ''
        text = u''
        username = ''
        edited = ''
        is_bot = False
        from_ho_id = ''
        sender_id = ''
        if reply['type'] == 'message' and 'subtype' in reply and reply['subtype'] == 'message_changed':
            if 'edited' in reply['message']:
                edited = '(msgupd)'
                user = reply['message']['edited']['user']
                text = reply['message']['text']
            else:
                # sent images from HO got an additional message_changed subtype without an 'edited' when slack renders the preview
                if 'username' in reply['message']:
                    # we ignore them as we already got the (unedited) message
                    return
                else:
                    print('slackrtm: unable to handle this kind of strange message type:\n%s' % pprint.pformat(reply))
                    return
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
                print("slackrtm: no text/user in reply: "+str(reply))
                return
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

        # now we check if the message has the hidden ho relay tag, extract and remove it
        hoidfmt = re.compile(r'^(.*) <ho://([^/]+)/([^|]+)\| >$', re.MULTILINE|re.DOTALL)
        match = hoidfmt.match(text)
        if match:
            text = match.group(1)
            from_ho_id = match.group(2)
            sender_id = match.group(3)

        if not is_bot:
            username = u'%s (Slack)' % self.get_username(user, user)
        elif sender_id != '':
            username = u'<a href="https://plus.google.com/%s">%s</a>' % (sender_id, username)

        response = u'<b>%s%s:</b> %s' % (username, edited, self.textToHtml(text))
        channel = None
        is_private = False
        if 'channel' in reply:
            channel = reply['channel']
        elif 'group' in reply:
            channel = reply['group']
            is_private = True
        if not channel:
            print('slackrtm: no channel or group in reply: %s' % pprint.pformat(reply))
            return
        file_attachment = None
        if 'file' in reply:
            if 'url' in reply['file']:
                file_attachment = reply['file']['url']
                response = u'%s\n%s' % (response, file_attachment)
            else:
                print('slackrtm: no "url" in reply, not adding public url:\n%s' % pprint.pformat(reply))

        if text.startswith('<@%s> whereami' % self.my_uid) or \
                text.startswith('<@%s>: whereami' % self.my_uid):
            message = u'@%s: you are in channel %s' % (username, channel)
            self.slack.api_call('chat.postMessage',
                                channel=channel,
                                text=message,
                                as_user=True,
                                link_names=True)

        for hoid, honame in self.hosinks.get(channel, []):
            if from_ho_id == hoid:
                print('slackrtm: NOT forwarding to HO %s: %s' % (hoid, response))
            else:
                print('slackrtm:     forwarding to HO %s: %s' % (hoid, response))
                if file_attachment:
                    try:
                        print('Downloading %s' % file_attachment)
                        filename = os.path.basename(file_attachment)
                        image_response = urllib.request.urlopen(file_attachment)
                        print('Uploading as %s' % filename)
                        image_id = self.bot._client.upload_image(image_response, filename=filename)
                        print('Sending HO message, image_id: %s' % image_id)
                        self.bot.send_message_segments(hoid, None, image_id=image_id)
                        return
                    except Exception as e:
                        print('slackrtm: Exception while uploading image: %s(%s)' % (e, str(e)))
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
            print("slackrtm: Sending to channel %s: %s" % (channel_id, message))
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
        t = threading.Thread(
            target=start_listening, 
            args=(bot, loop, sinkConfig)
            )
        t.daemon = True
        t.start()
        threads.append(t)
    logging.info(_("_start_slackrtm_sinks(): %d sink thread(s) started" % len(threads)))


def start_listening(bot, loop, config):
    print('slackrtm: start_listening()')
    asyncio.set_event_loop(loop)

    try:
        listener = SlackRTM(config, bot, threaded=True)
        last_ping = 0
        while True:
            replies = listener.rtm_read()
            for t in threading.enumerate():
                if t.name == listener.threadname and t != threading.current_thread():
                    print("slackrtm: I'm to old for this shit! Let's make space for the new guy: %s" % pprint.pformat(t))
                    return
            if len(replies):
                if 'type' in replies[0]:
                    if replies[0]['type'] == 'hello':
                        #print('slackrtm: ignoring first replies including type=hello message to avoid message duplication: %s...' % str(replies)[:30])
                        continue
            for reply in replies:
                try:
                    listener.handle_reply(reply)
                except Exception as e:
                    print('slackrtm: unhandled exception during handle_reply(): %s\n%s' % (str(e), pprint.pformat(reply)))
            now = int(time.time())
            if now > last_ping + 3:
                listener.ping()
                last_ping = now
            time.sleep(.1)
    except KeyboardInterrupt:
        # close, nothing to do
        return
    except WebSocketConnectionClosedException as e:
        print('slackrtm: start_listening(): got WebSocketConnectionClosedException("%s")' % str(e))
        return start_listening(bot, loop, config)
    except Exception as e:
        print('slackrtm: start_listening(): unhandled exception: %s' % str(e))
    return


#@asyncio.coroutine
def _handle_slackout(bot, event, command):
    slack_sink = bot.get_config_option('slackrtm')
    if not isinstance(slack_sink, list):
        return
    for sinkConfig in slack_sink:
        try:
            slackout = SlackRTM(sinkConfig, bot)
            slackout.handle_ho_message(event)
            time.sleep(.1)
        except Exception as e:
            print('slackrtm: _handle_slackout threw: %s' % str(e))

#@asyncio.coroutine
def _handle_membership_change(bot, event, command):
    slack_sink = bot.get_config_option('slackrtm')
    if not isinstance(slack_sink, list):
        return
    for sinkConfig in slack_sink:
        try:
            slackout = SlackRTM(sinkConfig, bot)
            slackout.handle_ho_membership(event)
            time.sleep(.1)
        except Exception as e:
            print('slackrtm: _handle_membership_change threw: %s' % str(e))


#@asyncio.coroutine
def _handle_rename(bot, event, command):
    slack_sink = bot.get_config_option('slackrtm')
    if not isinstance(slack_sink, list):
        return
    for sinkConfig in slack_sink:
        try:
            slackout = SlackRTM(sinkConfig, bot)
            slackout.handle_ho_rename(event)
            time.sleep(.1)
        except Exception as e:
            print('slackrtm: _handle_rename threw: %s' % str(e))
