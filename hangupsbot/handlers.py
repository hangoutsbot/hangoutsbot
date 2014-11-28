import logging, shlex, unicodedata, asyncio

import hangups

from commands import command


class MessageHandler(object):
    """Handle Hangups conversation events"""

    def __init__(self, bot, bot_command='/bot'):
        self.bot = bot
        self.bot_command = bot_command

    @staticmethod
    def word_in_text(word, text):
        """Return True if word is in text"""
        # Transliterate unicode characters to ASCII and make everything lowercase
        word = unicodedata.normalize('NFKD', word).encode('ascii', 'ignore').decode().lower()
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()

        # Replace delimiters in text with whitespace
        for delim in '.,:;!?':
            text = text.replace(delim, ' ')

        return True if word in text.split() else False

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
                # handle @mentions
                yield from self.handle_mention(event)

                # Forward messages
                yield from self.handle_forward(event)

                # Send automatic replies
                yield from self.handle_autoreply(event)

    @asyncio.coroutine
    def handle_command(self, event):
        """Handle command messages"""
        # Test if command handling is enabled
        if not self.bot.get_config_suboption(event.conv_id, 'commands_enabled'):
            return

        # Parse message
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
                                      '{}: I\'m sorry, Dave. I\'m afraid I can\'t do that.'.format(event.user.full_name))
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
                    if self.word_in_text(kw, event.text) or kw == "*":
                        self.bot.send_message(event.conv, sentence)
                        break

    @asyncio.coroutine
    def handle_mention(self, event):
        """handle @mention"""
        occurrences = [word for word in event.text.split() if word.startswith('@')]
        if len(occurrences) > 0:
            for word in occurrences:
                # strip all special characters
                cleaned_name = ''.join(e for e in word if e.isalnum())
                yield from command.run(self.bot, event, *["mention", cleaned_name])
 
