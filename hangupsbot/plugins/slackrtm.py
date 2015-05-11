import time
import re

from threading import Thread
from hangups.ui.utils import get_conv_name
from slackclient import SlackClient

import asyncio
import logging
import hangups

import emoji

""" SlackRTM plugin for listening to hangouts and slack and syncing messages between the two.
config.json will have to be configured as follows:
"slackrtm": [{
  "key": SLACK_API_KEY,
  "synced_conversations": [
  ["SLACK_CHANNEL_ID1", "CONV_ID1"],
  ["SLACK_CHANNEL_ID1", "CONV_ID1"]
  ]
}]

You can (theoretically) set up as many slack sinks per bot as you like, by extending the list"""


global_data = None

usernames = {}
channelnames = {}

def _initialise(Handlers, bot=None):
    global global_data
    if bot:
        _start_slackrtm_sinks(bot)
    else:
        print("slackrtm: Slack sinks could not be initialized.")
    Handlers.register_handler(_handle_slackout)
    Handlers.register_handler(_handle_membership_change, type="membership")
    global_data = 'init'
    return []

def _start_slackrtm_sinks(bot):
    global global_data
    print('slackrtm: start_slackrtm_sinks(): global_data=%s' % str(global_data))
    global_data = 'start_slackrtm_sinks'

    # Start and asyncio event loop
    loop = asyncio.get_event_loop()

    slack_sink = bot.get_config_option('slackrtm')
    itemNo = -1
    threads = []

    if isinstance(slack_sink, list):
        for sinkConfig in slack_sink:
            itemNo += 1

            # start up slack listener in a separate thread
            t = Thread(target=start_listening, args=(
              bot,
              loop,
              sinkConfig))

            t.daemon = True
            t.start()

            threads.append(t)

    message = _("_start_slackrtm_sinks(): {} sink thread(s) started").format(len(threads))
    logging.info(message)

def start_listening(bot=None, loop=None, config=None):
    global global_data, usernames, channelnames
    print('slackrtm: start_listening(): global_data=%s' % str(global_data))
    global_data = 'start_listening'

    if not bot or not config:
        return

    if loop:
        asyncio.set_event_loop(loop)

    try:
        slack_client = SlackClient(config["key"])
        slack_client.rtm_connect()
        for u in slack_client.server.login_data['users']:
            usernames[u['id']] = u['name']
        for c in slack_client.server.login_data['channels']:
            channelnames[c['id']] = c['name']
        my_uid = slack_client.server.login_data['self']['id']
        last_ping = 0
        while True:
            replies = slack_client.rtm_read()
            if len(replies):
                if 'type' in replies[0]:
                    if replies[0]['type'] == 'hello':
                        print('slackrtm: ignoring first replies including type=hello message to avoid message duplication: %s' % str(replies))
                        continue
            if len(replies) > 0:
                if len(replies) == 1 and replies[0]['type'] in ['pong', 'presence_change', 'user_typing']:
                    pass
                else:
                    print('slackrtm: replies=%s' % str(replies))
            for reply in replies:
                try:
                    handle_reply(reply, bot, config, my_uid)
                except Exception as e:
                    print('slackrtm: unhandled exception during handle_reply(%s): %s' % (str(reply), str(e)))
            now = int(time.time())
            if now > last_ping + 3:
                slack_client.server.ping()
                last_ping = now
            time.sleep(.1)
            
    except KeyboardInterrupt:
        # close, nothing to do
        return
    except Exception as e:
        print('slackrtm: start_listening(): unhandled exception: %s' % str(e))

    return

def matchReference(match):
    global usernames, channelnames
    out = ""
    linktext = ""
    if match.group(5) == '|':
        linktext = match.group(6)
    if match.group(2) == '@':
        if linktext != "":
            out = linktext
        else:
            out = "@%s" % usernames.get(match.group(3), 'unknown:%s' % match.group(3))
    elif match.group(2) == '#':
        if linktext != "":
            out = linktext
        else:
            out = "#%s" % channelnames.get(match.group(3), 'unknown:%s' % match.group(3))
    else:
        if linktext != "":
            out += linktext + ":"
        out += match.group(1)
    return out

def textToHtml(text):
    reffmt = re.compile('<((.)([^|>]*))((\|)([^>]*)|([^>]*))>')
    text = reffmt.sub(matchReference, text)
    text = emoji.emojize(text)
    bfmt = re.compile(r'\*([^\*]*)\*')
    text = bfmt.sub(r'<b>\1</b>', text)
    ifmt = re.compile(r'_([^_]*)_')
    text = ifmt.sub(r'<i>\1</i>', text)
    text = text.replace("\r\n", "\n")
    text = text.replace("\n", " <br/>\n")
    return text

def handle_reply(reply, bot, config, my_uid):
    if not 'type' in reply:
        print("slackrtm: No 'type' in reply:")
        print("slackrtm: "+str(reply))
        return

    if reply['type'] in ['pong', 'presence_change',  'user_typing']:
        # we ignore pong's as they are only answers for our pings
        return

    edited = ''
    if reply['type'] == 'message' and 'subtype' in reply and reply['subtype'] == 'message_changed':
        edited = '(msgupd)'
        reply['user'] = reply['message']['edited']['user']
        reply['text'] = reply['message']['text']

    if not 'text' in reply or not 'user' in reply:
        print("slackrtm: no text/user in reply: "+str(reply))
        return

    if my_uid == reply["user"]:
        print("slackrtm: ignoring our own messages")
        return

    print("slackrtm: handle_reply(%s)" % str(reply)[:200])
    if reply['user'] in usernames:
        username = usernames[reply['user']]
    else:
        print('slackbot: could not find user: %s' % str(reply['user']))
        username = str(reply['user'])
    response = "<b>%s%s:</b> %s" % (username, edited, textToHtml(reply["text"]))
    channel = None
    is_private = False
    if 'channel' in reply:
        channel = reply['channel']
    elif 'group' in reply:
        channel = reply['group']
        is_private = True
    if not channel:
        print('slackrtm: no channel or group in respone')
        return

    for conv in config["synced_conversations"]:
        if conv[0] == channel:
            print('slackrtm: found slack channel, forwarding to HO %s: %s' % (str(conv[1]), str(response)))
            if not bot.send_html_to_user(conv[1], response):
                bot.send_html_to_conversation(conv[1], response)


class SlackoutHandler(object):

    def __init__(self, config):
        try:
            slackkey = config["key"]
            self.convlist = config["synced_conversations"]
        except Exception as e:
            print("slackrtm: Could not handle slackout, is config.json properly configured?")
            return
        self.slack_client = SlackClient(slackkey)
        self.slack_client.rtm_connect()

    def findChannel(self, event):
        channel_id = None
        for conv in self.convlist:
            if event.conv_id in conv[1]:
                channel_id = conv[0]
        channel = None
        for c in self.slack_client.server.channels:
            if c.id == channel_id:
                channel = c
        return channel


@asyncio.coroutine
def _handle_slackout(bot, event, command):
    global global_data
    print('slackrtm: handle_slackout(): global_data=%s' % str(global_data))
    global_data = 'handle_slackout: %s' % event.text
    print("Got message from HO: %s" % event.conv_id)

    """forward messages to slack over webhook"""

    slack_sink = bot.get_config_option('slackrtm')

    if not isinstance(slack_sink, list):
        return
    for sinkConfig in slack_sink:
        try:
            channel_id = None
            for conv in sinkConfig['synced_conversations']:
                if conv[1] == event.conv_id:
                    channel_id = conv[0]
            if not channel_id:
                continue

            fullname = event.user.full_name
            try:
                response = yield from bot._client.getentitybyid([event.user_id.chat_id])
                photo_url = "http:" + response.entities[0].properties.photo_url
            except Exception as e:
                print("slackrtm: Could not pull avatar for %s: %s" %(fullname, str(e)))

            print("slackrtm: Sending to channel %s: %s" % (channel_id, event.text))
            slack = SlackClient(sinkConfig['key'])
            slack.api_call('chat.postMessage',
                           channel=channel_id,
                           text=event.text,
                           username=fullname,
                           link_names=True,
                           icon_url=photo_url)
            #client.chat_post_message(channel, event.text, username=fullname, icon_url=photo_url)
            time.sleep(.1)
        except Exception as e:
            print('slackrtm: SlackoutHandler threw: %s' % str(e))


@asyncio.coroutine
def _handle_membership_change(bot, event, command):
    global global_data
    print('slackrtm: handle_membership_change(): global_data=%s' % str(global_data))
    print('slackrtm: event:')

    # Generate list of added or removed users
    links = []
    for user_id in event.conv_event.participant_ids:
        user = event.conv.get_user(user_id)
        print('adding user %s' % user.full_name)
        links.append('<https://plus.google.com/%s/about|%s>' % (user.id_.chat_id, user.full_name))
    names = ', '.join(links)

    # JOIN
    if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        invitee = '<https://plus.google.com/%s/about|%s>' % (event.user_id.chat_id, event.user.full_name)
        message = '%s has added %s' % (invitee, names)
    # LEAVE
    else:
        message = '%s has left' % names
    print('slackrtm: %s' % message)

    slack_sink = bot.get_config_option('slackrtm')

    if not isinstance(slack_sink, list):
        return
    for sinkConfig in slack_sink:
        try:
            channel_id = None
            for conv in sinkConfig['synced_conversations']:
                if conv[1] == event.conv_id:
                    channel_id = conv[0]
            if not channel_id:
                continue

            print("slackrtm: Sending to channel %s: %s" % (channel_id, message))
            slack = SlackClient(sinkConfig['key'])
            slack.api_call('chat.postMessage',
                           channel=channel_id,
                           text=message,
                           as_user=True,
                           link_names=True)
            time.sleep(.1)
        except Exception as e:
            print('slackrtm: SlackoutHandler threw: %s' % str(e))
