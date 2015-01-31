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

        self._extra_handlers = { "message":[], "membership":[], "rename":[], "sending":[] }


    def register_handler(self, function, type="message"):
        """plugins call this to preload any handlers to be used by MessageHandler"""
        print('register_handler(): "{}" registered for "{}"'.format(function.__name__, type))
        self._extra_handlers[type].append(function)


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
    def handle_chat_message(self, event):
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

                # Send automatic replies
                yield from self.handle_autoreply(event)

            # handlers from plugins
            if "message" in self._extra_handlers:
                for function in self._extra_handlers["message"]:
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

    @asyncio.coroutine
    def handle_chat_membership(self, event):
        """Handle conversation membership change"""

        # handlers from plugins
        if "membership" in self._extra_handlers:
            for function in self._extra_handlers["membership"]:
                yield from function(self.bot, event, command)

        # Don't handle events caused by the bot himself
        if event.user.is_self:
            return

        sync_room_list = self.bot.get_config_suboption(event.conv_id, 'sync_rooms')

        # Test if watching for membership changes is enabled
        if not self.bot.get_config_suboption(event.conv_id, 'membership_watching_enabled'):
            return

        # Generate list of added or removed users
        event_users = [event.conv.get_user(user_id) for user_id
                       in event.conv_event.participant_ids]
        names = ', '.join([user.full_name for user in event_users])

        # JOIN
        if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
            self.bot.send_message(event.conv, '{}: Welcome!'.format(names))
            if event.conv_id in sync_room_list:
                for dst in sync_room_list:
                    try:
                        conv = self.bot._conv_list.get(dst)
                    except KeyError:
                        continue
                    if not dst == event.conv_id:
                        self.bot.send_message(conv, '{} has added {} to the Syncout'.format(event.user.full_name, names))
        # LEAVE
        else:
            self.bot.send_message(event.conv, 'Goodbye {}! =('.format(names))
            if event.conv_id in sync_room_list:
                for dst in sync_room_list:
                    try:
                        conv = self.bot._conv_list.get(dst)
                    except KeyError:
                        continue
                    if not dst == event.conv_id:
                        self.bot.send_message(conv, '{} has left the Syncout'.format(names))

    @asyncio.coroutine
    def handle_chat_rename(self, event):
        # handlers from plugins
        if "rename" in self._extra_handlers:
            for function in self._extra_handlers["rename"]:
                yield from function(self.bot, event, command)