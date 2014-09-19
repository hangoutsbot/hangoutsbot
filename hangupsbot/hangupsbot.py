#!/usr/bin/env python
import os, sys, argparse, logging, shutil, asyncio

import appdirs
import hangups
from hangups.utils import get_conv_name

import hangupsbot.config
import hangupsbot.handlers


__version__ = '1.1'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


class ConversationEvent(object):
    """Cenversation event"""
    def __init__(self, bot, conv_event):
        self.conv_event = conv_event
        self.conv_id = conv_event.conversation_id
        self.conv = bot._conv_list.get(self.conv_id)
        self.user_id = conv_event.user_id
        self.user = self.conv.get_user(self.user_id)
        self.timestamp = conv_event.timestamp
        self.text = conv_event.text.strip() if isinstance(conv_event, hangups.ChatMessageEvent) else ''

    def print_debug(self):
        """Print informations about conversation event"""
        print('Conversation ID: {}'.format(self.conv_id))
        print('Conversation name: {}'.format(get_conv_name(self.conv, truncate=True)))
        print('User ID: {}'.format(self.user_id))
        print('User name: {}'.format(self.user.full_name))
        print('Timestamp: {}'.format(self.timestamp.astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')))
        print('Text: {}'.format(self.text))
        print()


class HangupsBot(object):
    """Hangouts bot listening on all conversations"""
    def __init__(self, cookies_path, config_path):
        # These are populated by on_connect when it's called.
        self._conv_list = None        # hangups.ConversationList
        self._user_list = None        # hangups.UserList
        self._message_handler = None  # MessageHandler

        # Load config file
        self.config = hangupsbot.config.Config(config_path)

        # Authenticate Google user and save auth cookies
        # (or load already saved cookies)
        try:
            cookies = hangups.auth.get_auth_stdin(cookies_path)
        except hangups.GoogleAuthError as e:
            print('Login failed ({})'.format(e))
            sys.exit(1)

        # Start Hangups client
        self._client = hangups.Client(cookies)
        self._client.on_connect.add_observer(self._on_connect)
        self._client.on_disconnect.add_observer(self._on_disconnect)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._client.connect())

    def handle_chat_message(self, conv_event):
        """Handle chat messages"""
        event = ConversationEvent(self, conv_event)
        asyncio.async(self._message_handler.handle(event))

    def handle_membership_change(self, conv_event):
        """Handle conversation membership change"""
        event = ConversationEvent(self, conv_event)

        # Test if watching for membership changes is enabled
        if not self.get_config_suboption(event.conv_id, 'membership_watching_enabled'):
            return

        # Generate list of added or removed users
        event_users = [event.conv.get_user(user_id) for user_id
                       in event.conv_event.participant_ids]
        names = ', '.join([user.full_name for user in event_users])

        # JOIN
        if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
            # Test if user who added new participants is admin
            admins_list = self.get_config_suboption(event.conv_id, 'admins')
            if event.user_id.chat_id in admins_list:
                self.send_message(event.conv,
                                  '{}: Ahoj, {} mezi nás!'.format(names,
                                                                  'vítejte' if len(event_users) > 1 else 'vítej'))
            else:
                segments = [hangups.ChatMessageSegment('!!! POZOR !!!', is_bold=True),
                            hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                            hangups.ChatMessageSegment('{} neoprávněně přidal do tohoto Hangoutu uživatele {}!'.format(
                                                       event.user.full_name, names)),
                            hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                            hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                            hangups.ChatMessageSegment('{}: Opusťte prosím urychleně tento Hangout!'.format(names))]
                self.send_message_segments(event.conv, segments)
        # LEAVE
        else:
            self.send_message(event.conv,
                              '{} nám {} košem :-( Řekněte pá pá!'.format(names,
                                                                          'dali' if len(event_users) > 1 else 'dal'))

    def handle_rename(self, conv_event):
        """Handle conversation rename"""
        event = ConversationEvent(self, conv_event)

        # Test if watching for conversation rename is enabled
        if not self.get_config_suboption(event.conv_id, 'rename_watching_enabled'):
            return

        # Only print renames for now...
        if event.conv_event.new_name == '':
            print('{} cleared the conversation name'.format(event.user.first_name))
        else:
            print('{} renamed the conversation to {}'.format(event.user.first_name, event.conv_event.new_name))

    def send_message(self, conversation, text):
        """"Send simple chat message"""
        self.send_message_segments(conversation, [hangups.ChatMessageSegment(text)])

    def send_message_segments(self, conversation, segments):
        """Send chat message segments"""
        # Ignore if the user hasn't typed a message.
        if len(segments) == 0:
            return
        # XXX: Exception handling here is still a bit broken. Uncaught
        # exceptions in _on_message_sent will only be logged.
        asyncio.async(
            conversation.send_message(segments)
        ).add_done_callback(self._on_message_sent)

    def list_conversations(self):
        """List all active conversations"""
        convs = sorted(self._conv_list.get_all(),
                       reverse=True, key=lambda c: c.last_modified)
        return convs

    def get_config_suboption(self, conv_id, option):
        """Get config suboption for conversation (or global option if not defined)"""
        try:
            suboption = self.config['conversations'][conv_id][option]
        except KeyError:
            try:
                suboption = self.config[option]
            except KeyError:
                suboption = None
        return suboption

    def _on_message_sent(self, future):
        """Handle showing an error if a message fails to send"""
        try:
            future.result()
        except hangups.NetworkError:
            print('Failed to send message!')

    def _on_connect(self, initial_data):
        """Handle connecting for the first time"""
        print('Connected!')
        self._message_handler = hangupsbot.handlers.MessageHandler(self)

        self._user_list = hangups.UserList(self._client,
                                           initial_data.self_entity,
                                           initial_data.entities,
                                           initial_data.conversation_participants)
        self._conv_list = hangups.ConversationList(self._client,
                                                   initial_data.conversation_states,
                                                   self._user_list,
                                                   initial_data.sync_timestamp)
        self._conv_list.on_event.add_observer(self._on_event)

        print('Conversations:')
        for c in self.list_conversations():
            print('  {} ({})'.format(get_conv_name(c, truncate=True), c.id_))
        print()

    def _on_event(self, conv_event):
        """Handle conversation events"""
        if isinstance(conv_event, hangups.ChatMessageEvent):
            self.handle_chat_message(conv_event)
        elif isinstance(conv_event, hangups.MembershipChangeEvent):
            self.handle_membership_change(conv_event)
        elif isinstance(conv_event, hangups.RenameEvent):
            self.handle_rename(conv_event)

    def _on_disconnect(self):
        """Handle disconnecting"""
        print('Connection lost!')


def main():
    """Main entry point"""
    # Build default paths for files.
    dirs = appdirs.AppDirs('hangupsbot', 'hangupsbot')
    default_log_path = os.path.join(dirs.user_data_dir, 'hangupsbot.log')
    default_cookies_path = os.path.join(dirs.user_data_dir, 'cookies.json')
    default_config_path = os.path.join(dirs.user_data_dir, 'config.json')

    # Configure argument parser
    parser = argparse.ArgumentParser(prog='hangupsbot',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d', '--debug', action='store_true',
                        help='log detailed debugging messages')
    parser.add_argument('--log', default=default_log_path,
                        help='log file path')
    parser.add_argument('--cookies', default=default_cookies_path,
                        help='cookie storage path')
    parser.add_argument('--config', default=default_config_path,
                        help='config storage path')
    args = parser.parse_args()

    # Create all necessary directories.
    for path in [args.log, args.cookies, args.config]:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            try:
                os.makedirs(directory)
            except OSError as e:
                sys.exit('Failed to create directory: {}'.format(e))

    # If there is no config file in user data directory, copy default one there
    if not os.path.isfile(args.config):
        try:
            shutil.copy(os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), 'config.json')),
                        args.config)
        except (OSError, IOError) as e:
            sys.exit('Failed to copy default config file: {}'.format(e))

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(filename=args.log, level=log_level, format=LOG_FORMAT)
    # asyncio's debugging logs are VERY noisy, so adjust the log level
    logging.getLogger('asyncio').setLevel(logging.WARNING)

    # Start Hangups bot
    HangupsBot(args.cookies, args.config)


if __name__ == '__main__':
    main()
