#!/usr/bin/env python3
import os, sys, argparse, logging, shutil, asyncio, time, signal

import appdirs
import hangups
from threading import Thread

from utils import simple_parse_to_segments, class_from_name
from hangups.ui.utils import get_conv_name

import config
import handlers

from sinks.listener import start_listening
#import sinks.gitlab.simplepush

__version__ = '1.1'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

class ConversationEvent(object):
    """Conversation event"""
    def __init__(self, bot, conv_event):
        self.conv_event = conv_event
        self.conv_id = conv_event.conversation_id
        self.conv = bot._conv_list.get(self.conv_id)
        self.event_id = conv_event.id_
        self.user_id = conv_event.user_id
        self.user = self.conv.get_user(self.user_id)
        self.timestamp = conv_event.timestamp
        self.text = conv_event.text.strip() if isinstance(conv_event, hangups.ChatMessageEvent) else ''

    def print_debug(self):
        """Print informations about conversation event"""
        print('Conversation ID: {}'.format(self.conv_id))
        print('Conversation name: {}'.format(get_conv_name(self.conv, truncate=True)))
        print('Event ID: {}'.format(self.event_id))
        print('User ID: {}'.format(self.user_id))
        print('User name: {}'.format(self.user.full_name))
        print('Timestamp: {}'.format(self.timestamp.astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')))
        print('Text: {}'.format(self.text))
        print()


class HangupsBot(object):
    """Hangouts bot listening on all conversations"""
    def __init__(self, cookies_path, config_path, max_retries=5):
        self._client = None
        self._cookies_path = cookies_path
        self._max_retries = max_retries

        # These are populated by on_connect when it's called.
        self._conv_list = None        # hangups.ConversationList
        self._user_list = None        # hangups.UserList
        self._message_handler = None  # MessageHandler

        # Load config file
        self.config = config.Config(config_path)

        # Handle signals on Unix
        # (add_signal_handler is not implemented on Windows)
        try:
            loop = asyncio.get_event_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, lambda: self.stop())
        except NotImplementedError:
            pass

    def login(self, cookies_path):
        """Login to Google account"""
        # Authenticate Google user and save auth cookies
        # (or load already saved cookies)
        try:
            cookies = hangups.auth.get_auth_stdin(cookies_path)
            return cookies
        except hangups.GoogleAuthError as e:
            print('Login failed ({})'.format(e))
            return False

    def run(self):
        """Connect to Hangouts and run bot"""
        cookies = self.login(self._cookies_path)
        if cookies:
            # Create Hangups client
            self._client = hangups.Client(cookies)
            self._client.on_connect.add_observer(self._on_connect)
            self._client.on_disconnect.add_observer(self._on_disconnect)

            # Initialise hooks
            self._load_hooks()

            # Start asyncio event loop
            loop = asyncio.get_event_loop()

            # Start threads for web sinks
            self._start_sinks(loop)

            # Connect to Hangouts
            # If we are forcefully disconnected, try connecting again
            for retry in range(self._max_retries):
                try:
                    loop.run_until_complete(self._client.connect())
                    sys.exit(0)
                except Exception as e:
                    print('Client unexpectedly disconnected:\n{}'.format(e))
                    print('Waiting {} seconds...'.format(5 + retry * 5))
                    time.sleep(5 + retry * 5)
                    print('Trying to connect again (try {} of {})...'.format(retry + 1, self._max_retries))
            print('Maximum number of retries reached! Exiting...')
        sys.exit(1)

    def stop(self):
        """Disconnect from Hangouts"""
        asyncio.async(
            self._client.disconnect()
        ).add_done_callback(lambda future: future.result())

    def handle_chat_message(self, conv_event):
        """Handle chat messages"""
        event = ConversationEvent(self, conv_event)
        self._execute_hook("on_chat_message", event)
        asyncio.async(self._message_handler.handle(event))

    def handle_membership_change(self, conv_event):
        """Handle conversation membership change"""
        event = ConversationEvent(self, conv_event)
        self._execute_hook("on_membership_change", event)

        # Don't handle events caused by the bot himself
        if event.user.is_self:
            return

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
                self.send_message(event.conv, '{}: welcome'.format(names))
            else:
                segments = [hangups.ChatMessageSegment('!!! ATTENTION !!!', is_bold=True),
                            hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                            hangups.ChatMessageSegment('{} added these users {}!'.format(
                                                       event.user.full_name, names)),
                            hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                            hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                            hangups.ChatMessageSegment('{}: please leave this hangout'.format(names))]
                self.send_message_segments(event.conv, segments)
        # LEAVE
        else:
            self.send_message(event.conv, '{}: left'.format(names))

    def handle_rename(self, conv_event):
        """Handle conversation rename"""
        event = ConversationEvent(self, conv_event)
        self._execute_hook("on_rename", event)

        # Don't handle events caused by the bot himself
        if event.user.is_self:
            return

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

    def send_message_parsed(self, conversation, html):
        segments = simple_parse_to_segments(html)
        self.send_message_segments(conversation, segments)

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
        try:
            _all_conversations = self._conv_list.get_all()
            convs = sorted(_all_conversations, reverse=True, key=lambda c: c.last_modified)
            logging.info("list_conversations() returned {} conversation(s)".format(len(convs)))
        except Exception as e:
            logging.warning("list_conversations()", e)
            raise

        return convs

    def get_config_option(self, option):
        try:
            option_value = self.config[option]
        except KeyError:
            option_value = None
        return option_value

    def get_config_suboption(self, conv_id, option):
        """Get config suboption for conversation (or global option if not defined)"""
        try:
            suboption = self.config['conversations'][conv_id][option]
        except KeyError:
            suboption = self.get_config_option(option)
        return suboption

    def print_conversations(self):
        print('Conversations:')
        for c in self.list_conversations():
            print('  {} ({}) u:{}'.format(get_conv_name(c, truncate=True), c.id_, len(c.users)))
            for u in c.users:
                print('    {} ({}) {}'.format(u.first_name, u.full_name, u.id_.chat_id))
        print()

    def get_1on1_conversation(self, chat_id):
        conversation = None
        for c in self.list_conversations():
            if len(c.users) == 2:
                for u in c.users:
                    if u.id_.chat_id == chat_id:
                        conversation = c
                        break
        return conversation

    def _start_sinks(self, shared_loop):
        jsonrpc_sinks = self.get_config_option('jsonrpc')
        itemNo = -1
        threads = []

        if isinstance(jsonrpc_sinks, list):
            for sinkConfig in jsonrpc_sinks:
                itemNo += 1

                try:
                    module = sinkConfig["module"].split(".")
                    if len(module) < 4:
                        print("config.jsonrpc[{}].module should have at least 4 packages {}".format(itemNo, module))
                        continue
                    module_name = ".".join(module[0:-1])
                    class_name = ".".join(module[-1:])
                    if not module_name or not class_name:
                        print("config.jsonrpc[{}].module must be a valid package name".format(itemNo))
                        continue

                    certfile = sinkConfig["certfile"]
                    if not certfile:
                        print("config.jsonrpc[{}].certfile must be configured".format(itemNo))
                        continue

                    name = sinkConfig["name"]
                    port = sinkConfig["port"]
                except KeyError as e:
                    print("config.jsonrpc[{}] missing keyword".format(itemNo), e)
                    continue

                # start up rpc listener in a separate thread
                print("thread starting: {}".format(module))
                t = Thread(target=start_listening, args=(
                  self,
                  shared_loop,
                  name,
                  port,
                  certfile,
                  class_from_name(module_name, class_name)))

                t.daemon = True
                t.start()

                threads.append(t)

        message = "{} sink thread(s) started".format(len(threads))
        logging.info(message)
        print(message)

    def _load_hooks(self):
        hook_packages = self.get_config_option('hooks')
        itemNo = -1
        self._hooks = []

        if isinstance(hook_packages, list):
            for hook_config in hook_packages:
                try:
                    module = hook_config["module"].split(".")
                    if len(module) < 4:
                        print("config.hooks[{}].module should have at least 4 packages {}".format(itemNo, module))
                        continue
                    module_name = ".".join(module[0:-1])
                    class_name = ".".join(module[-1:])
                    if not module_name or not class_name:
                        print("config.hooks[{}].module must be a valid package name".format(itemNo))
                        continue
                except KeyError as e:
                    print("config.hooks[{}] missing keyword".format(itemNo), e)
                    continue

                theClass = class_from_name(module_name, class_name)
                theClass._bot = self
                if "config" in hook_config:
                    # allow separate configuration file to be loaded
                    theClass._config = hook_config["config"]

                if theClass.init():
                    print("hook inited: {}".format(module))
                    self._hooks.append(theClass)
                else:
                    print("hook failed to initialise")

        message = "{} hook(s) loaded".format(len(self._hooks))
        logging.info(message)
        print(message)

    def _on_message_sent(self, future):
        """Handle showing an error if a message fails to send"""
        try:
            future.result()
        except hangups.NetworkError:
            print('Failed to send message!')

    def _on_connect(self, initial_data):
        """Handle connecting for the first time"""
        print('Connected!')
        self._message_handler = handlers.MessageHandler(self)

        self._user_list = hangups.UserList(self._client,
                                           initial_data.self_entity,
                                           initial_data.entities,
                                           initial_data.conversation_participants)
        self._conv_list = hangups.ConversationList(self._client,
                                                   initial_data.conversation_states,
                                                   self._user_list,
                                                   initial_data.sync_timestamp)
        self._conv_list.on_event.add_observer(self._on_event)

        self.print_conversations()

    def _on_event(self, conv_event):
        """Handle conversation events"""

        self._execute_hook("on_event", conv_event)

        if isinstance(conv_event, hangups.ChatMessageEvent):
            self.handle_chat_message(conv_event)

        elif isinstance(conv_event, hangups.MembershipChangeEvent):
            self.handle_membership_change(conv_event)

        elif isinstance(conv_event, hangups.RenameEvent):
            self.handle_rename(conv_event)

    def _execute_hook(self, funcname, parameters=None):
        for hook in self._hooks:
            method = getattr(hook, funcname, None)
            if method:
                try:
                    method(parameters)
                except Exception as e:
                    message = "_execute_hooks()", hook, e
                    logging.warning(message)
                    print(message)

    def _on_disconnect(self):
        """Handle disconnecting"""
        print('Connection lost!')

    def external_send_message(self, conversation_id, text):
        conversation = self._conv_list.get(conversation_id)
        print('sending message, conversation name:', get_conv_name(conversation))
        self.send_message(conversation, text)

    def external_send_message_parsed(self, conversation_id, html):
        conversation = self._conv_list.get(conversation_id)
        print('sending parsed message, conversation name:', get_conv_name(conversation))
        self.send_message_parsed(conversation, html)

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
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(filename=args.log, level=log_level, format=LOG_FORMAT)
    # asyncio's debugging logs are VERY noisy, so adjust the log level
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    # hangups log is quite verbose too, suppress so we can debug the bot
    logging.getLogger('hangups').setLevel(logging.WARNING)

    # initialise the bot
    bot = HangupsBot(args.cookies, args.config)
    bot.run()


if __name__ == '__main__':
    main()
