import logging, shlex, unicodedata, asyncio

import hangups

import re, time

from commands import command

from hangups.ui.utils import get_conv_name

class MessageHandler(object):
    """Handle Hangups conversation events"""

    def __init__(self, bot, bot_command='/bot'):
        self.bot = bot
        self.bot_command = bot_command

        self.last_event_id = 'none' # recorded last event to avoid re-syncing
        self.last_user_id = 'none' # recorded last user to allow message compression
        self.last_chatroom_id = 'none' # recorded last chat room to prevent room crossover
        self.last_time_id = 0 # recorded timestamp of last chat to 'expire' chats

        self._extra_handlers = [];
        command.attach_extra_handlers(self) 


    @staticmethod
    def words_in_text(word, text):
        """Return True if word is in text"""
        # Transliterate unicode characters to ASCII and make everything lowercase
        word = unicodedata.normalize('NFKD', word).encode('ascii', 'ignore').decode().lower()
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()

        # Replace delimiters in text with whitespace
        for delim in '.,:;!?':
            text = text.replace(delim, ' ')

        return True if word in text else False

    @asyncio.coroutine
    def handle(self, event):
        """Handle conversation event"""
        if logging.root.level == logging.DEBUG:
            event.print_debug()

        if not event.user.is_self and event.text:
            if event.text.split()[0].lower() == self.bot_command:
                # Run command
                yield from self.handle_command(event)
            else:
                # Forward messages
                yield from self.handle_forward(event)

                # Sync messages
                yield from self.handle_syncing(event)

                # Send automatic replies
                yield from self.handle_autoreply(event)

                for function in self._extra_handlers:
                    yield from function(self.bot, event, command)


    @asyncio.coroutine
    def handle_command(self, event):
        """Handle command messages"""
        # Test if command handling is enabled
        if not self.bot.get_config_suboption(event.conv_id, 'commands_enabled'):
            return

        # Parse message
        event.text = event.text.replace(u'\xa0', u' ') # convert non-breaking space in Latin1 (ISO 8859-1)
        line_args = shlex.split(event.text, posix=False)

        # Test if command length is sufficient
        if len(line_args) < 2:
            self.bot.send_message(event.conv,
                                  '{}: missing parameter(s)'.format(event.user.full_name))
            return

        # Test if user has permissions for running command
        commands_admin_list = self.bot.get_config_suboption(event.conv_id, 'commands_admin')
        if commands_admin_list and line_args[1].lower() in commands_admin_list:
            admins_list = self.bot.get_config_suboption(event.conv_id, 'admins')
            if event.user_id.chat_id not in admins_list:
                self.bot.send_message(event.conv,
                                      '{}: I\'m sorry. I\'m afraid I can\'t do that.'.format(event.user.full_name))
                return

        # Run command
        yield from command.run(self.bot, event, *line_args[1:])

    @asyncio.coroutine
    def handle_syncing(self, event):
        """Handle message syncing"""
        if not self.bot.get_config_option('syncing_enabled'):
            return
        sync_room_list = self.bot.get_config_suboption(event.conv_id, 'sync_rooms')

        if not sync_room_list:
            return # Sync room not configured, returning

        if self.last_event_id == event.conv_event.id_:
            return # This event has already been synced
        self.last_event_id = event.conv_event.id_

        if event.conv_id in sync_room_list:
            print('>> message from synced room');
            link = 'https://plus.google.com/u/0/{}/about'.format(event.user_id.chat_id)

            ### Deciding how to relay the name across

            # Checking that it hasn't timed out since last message
            timeout_threshold = 30.0 # Number of seconds to allow the timeout
            if time.time() - self.last_time_id > timeout_threshold:
                timeout = True
            else:
                timeout = False

            # Checking if the user is the same as the one who sent the previous message
            if self.last_user_id in event.user_id.chat_id:
                sameuser = True
            else:
                sameuser = False

            # Checking if the room is the same as the room where the last message was sent
            if self.last_chatroom_id in event.conv_id:
                sameroom = True
            else:
                sameroom = False

            if (not sameroom or timeout or not sameuser) and \
                (self.bot.memory.exists(['user_data', event.user_id.chat_id, "nickname"])):
                # Now check if there is a nickname set

                try:
                    fullname = '{0} ({1})'.format(event.user.full_name.split(' ', 1)[0]
                        , self.bot.get_memory_suboption(event.user_id.chat_id, 'nickname'))
                except TypeError:
                    fullname = event.user.full_name
            elif sameroom and sameuser and not timeout:
                fullname = '>>'
            else:
                fullname = event.user.full_name

            ### Name decided and put into variable 'fullname'

            segments = [hangups.ChatMessageSegment('{0}'.format(fullname), hangups.SegmentType.LINK,
                                                   link_target=link, is_bold=True),
                        hangups.ChatMessageSegment(': ', is_bold=True)]

            # Append links to attachments (G+ photos) to forwarded message
            if event.conv_event.attachments:
                segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
                segments.extend([hangups.ChatMessageSegment(link, hangups.SegmentType.LINK, link_target=link)
                                 for link in event.conv_event.attachments])

            # Make links hyperlinks and send message
            URL_RE = re.compile(r'https?://\S+')
            for segment in event.conv_event.segments:
                last = 0
                for match in URL_RE.finditer(segment.text):
                    if match.start() > last:
                        segments.append(hangups.ChatMessageSegment(segment.text[last:match.start()]))
                    segments.append(hangups.ChatMessageSegment(match.group(), link_target=match.group()))
                    last = match.end()
                if last != len(segment.text):
                    segments.append(hangups.ChatMessageSegment(segment.text[last:]))

            for dst in sync_room_list:
                try:
                    conv = self.bot._conv_list.get(dst)
                except KeyError:
                    continue
                if not dst == event.conv_id:
                    self.bot.send_message_segments(conv, segments)

            self.last_user_id = event.user_id.chat_id
            self.last_time_id = time.time()
            self.last_chatroom_id = event.conv_id

    @asyncio.coroutine
    def handle_forward(self, event):
        """Handle message forwarding"""
        # Test if message forwarding is enabled
        if not self.bot.get_config_suboption(event.conv_id, 'forwarding_enabled'):
            return

        forward_to_list = self.bot.get_config_suboption(event.conv_id, 'forward_to')
        if forward_to_list:
            for dst in forward_to_list:
                try:
                    conv = self.bot._conv_list.get(dst)
                except KeyError:
                    continue

                # Prepend forwarded message with name of sender
                link = 'https://plus.google.com/u/0/{}/about'.format(event.user_id.chat_id)
                segments = [hangups.ChatMessageSegment(event.user.full_name, hangups.SegmentType.LINK,
                                                       link_target=link, is_bold=True),
                            hangups.ChatMessageSegment(': ', is_bold=True)]
                # Copy original message segments
                segments.extend(event.conv_event.segments)
                # Append links to attachments (G+ photos) to forwarded message
                if event.conv_event.attachments:
                    segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
                    segments.extend([hangups.ChatMessageSegment(link, hangups.SegmentType.LINK, link_target=link)
                                     for link in event.conv_event.attachments])
                self.bot.send_message_segments(conv, segments)

    @asyncio.coroutine
    def handle_autoreply(self, event):
        """Handle autoreplies to keywords in messages"""
        # Test if autoreplies are enabled
        if not self.bot.get_config_suboption(event.conv_id, 'autoreplies_enabled'):
            return

        autoreplies_list = self.bot.get_config_suboption(event.conv_id, 'autoreplies')
        if autoreplies_list:
            for kwds, sentence in autoreplies_list:
                for kw in kwds:
                    if self.words_in_text(kw, event.text) or kw == "*":
                        self.bot.send_message(event.conv, sentence)
                        break