#!/usr/bin/env python3
import os, sys, argparse, logging, shutil, asyncio, time, signal

import gettext
gettext.install('hangupsbot', localedir=os.path.join(os.path.dirname(__file__), 'locale'))

import appdirs
import hangups

from utils import simple_parse_to_segments, class_from_name
from hangups.ui.utils import get_conv_name
try:
    from hangups.schemas import OffTheRecordStatus
except ImportError:
    print("WARNING: hangups library out of date!")

import config
import handlers
import version
from commands import command
from handlers import handler # shim for handler decorator

import hooks
import sinks
import plugins


LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


class SuppressHandler(Exception):
    pass

class SuppressAllHandlers(Exception):
    pass

class SuppressEventHandling(Exception):
    pass

class HangupsBotExceptions:
    def __init__(self):
        self.SuppressHandler = SuppressHandler
        self.SuppressAllHandlers = SuppressAllHandlers
        self.SuppressEventHandling = SuppressEventHandling


class FakeConversation(object):
    def __init__(self, _client, id_):
        self._client = _client
        self.id_ = id_

    @asyncio.coroutine
    def send_message(self, segments, image_id=None, otr_status=None):
        if segments:
            serialised_segments = [seg.serialize() for seg in segments]
        else:
            serialised_segments = None

        try:
            yield from self._client.sendchatmessage(self.id_, serialised_segments, image_id=image_id, otr_status=otr_status)
        except (TypeError, AttributeError):
            # in the event the hangups library doesn't support image sending
            try:
                yield from self._client.sendchatmessage(self.id_, serialised_segments, otr_status=otr_status)
            except (TypeError, AttributeError):
                # in the event the hangups library doesn't support otr_status (note that image support assumes otr_status support)
                yield from self._client.sendchatmessage(self.id_, serialised_segments)


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
        print(_('eid/dtime: {}/{}').format(self.event_id, self.timestamp.astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')))
        print(_('cid/cname: {}/{}').format(self.conv_id, get_conv_name(self.conv, truncate=True)))
        if(self.user_id.chat_id == self.user_id.gaia_id):
            print(_('uid/uname: {}/{}').format(self.user_id.chat_id, self.user.full_name))
        else:
            print(_('uid/uname: {}!{}/{}').format(self.user_id.chat_id, self.user_id.gaia_id, self.user.full_name))
        print(_('txtlen/tx: {}/{}').format(len(self.text), self.text))
        print(_('eventdump: completed --8<--'))


class HangupsBot(object):
    """Hangouts bot listening on all conversations"""
    def __init__(self, cookies_path, config_path, max_retries=5, memory_file=None):
        self.Exceptions = HangupsBotExceptions()

        self.shared = {} # safe place to store references to objects

        self._client = None
        self._cookies_path = cookies_path
        self._max_retries = max_retries

        # These are populated by on_connect when it's called.
        self._conv_list = None # hangups.ConversationList
        self._user_list = None # hangups.UserList
        self._handlers = None # handlers.py::EventHandler

        self._cache_event_id = {} # workaround for duplicate events

        # Load config file
        self.config = config.Config(config_path)

        # load in previous memory, or create new one
        self.memory = None
        if memory_file:
            print(_("HangupsBot: memory file will be used: {}").format(memory_file))
            self.memory = config.Config(memory_file)
            if not os.path.isfile(memory_file):
                try:
                    print(_("creating memory file: {}").format(memory_file))
                    self.memory.force_taint()
                    self.memory.save()
                except (OSError, IOError) as e:
                    sys.exit(_('failed to create default memory file: {}').format(e))

        # Handle signals on Unix
        # (add_signal_handler is not implemented on Windows)
        try:
            loop = asyncio.get_event_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, lambda: self.stop())
        except NotImplementedError:
            pass

    def register_shared(self, id, objectref, forgiving=False):
        if id in self.shared:
            message = _("{} already registered in shared").format(id)
            if forgiving:
                print(message)
                logging.info(message)
            else:
                raise RuntimeError(message)
        self.shared[id] = objectref
        plugins.tracking.register_shared(id, objectref, forgiving=forgiving)

    def call_shared(self, id, *args, **kwargs):
        object = self.shared[id]
        if hasattr(object, '__call__'):
            return object(*args, **kwargs)
        else:
            return object

    def login(self, cookies_path):
        """Login to Google account"""
        # Authenticate Google user and save auth cookies
        # (or load already saved cookies)
        try:
            cookies = hangups.auth.get_auth_stdin(cookies_path)
            return cookies
        except hangups.GoogleAuthError as e:
            print(_('Login failed ({})').format(e))
            return False

    def run(self):
        """Connect to Hangouts and run bot"""
        cookies = self.login(self._cookies_path)
        if cookies:
            # Start asyncio event loop
            loop = asyncio.get_event_loop()

            # initialise pluggable framework
            hooks.load(self)
            sinks.start(self, loop)

            # Connect to Hangouts
            # If we are forcefully disconnected, try connecting again
            for retry in range(self._max_retries):
                try:
                    # create Hangups client (recreate if its a retry)
                    self._client = hangups.Client(cookies)
                    self._client.on_connect.add_observer(self._on_connect)
                    self._client.on_disconnect.add_observer(self._on_disconnect)

                    loop.run_until_complete(self._client.connect())
                    sys.exit(0)
                except Exception as e:
                    logging.exception(_("unrecoverable low-level error"))
                    print(_('Client unexpectedly disconnected:\n{}').format(e))
                    print(_('Waiting {} seconds...').format(5 + retry * 5))
                    time.sleep(5 + retry * 5)
                    print(_('Trying to connect again (try {} of {})...').format(retry + 1, self._max_retries))
            print(_('Maximum number of retries reached! Exiting...'))
        sys.exit(1)

    def stop(self):
        """Disconnect from Hangouts"""
        asyncio.async(
            self._client.disconnect()
        ).add_done_callback(lambda future: future.result())

    def send_message(self, conversation, text, context=None):
        """"Send simple chat message"""
        self.send_message_segments(
            conversation,
            [hangups.ChatMessageSegment(text)],
            context)

    def send_message_parsed(self, conversation, html, context=None):
        segments = simple_parse_to_segments(html)
        self.send_message_segments(conversation, segments, context)

    def send_message_segments(self, conversation, segments, context=None, image_id=None):
        """Send chat message segments"""
        otr_status = None

        # Ignore if the user hasn't typed a message.
        if type(segments) is list and len(segments) == 0:
            return


        # add default context if none exists
        if not context:
            context = {}
        context["base"] = self._messagecontext_legacy()

        # reduce conversation to the only things we need: the id and history
        if isinstance(conversation, (FakeConversation, hangups.conversation.Conversation)):
            conversation_id = conversation.id_
            # Turn history off if it's off in the conversation
            try:
                otr_status = (OffTheRecordStatus.OFF_THE_RECORD
                    if conversation.is_off_the_record
                    else OffTheRecordStatus.ON_THE_RECORD)
            except (KeyError, AttributeError):
                pass
        elif isinstance(conversation, str):
            conversation_id = conversation
            # Turn history off if it's off in the conversation
            try:
                otr_status = (OffTheRecordStatus.OFF_THE_RECORD
                    if self._conv_list.get(conversation).is_off_the_record
                    else OffTheRecordStatus.ON_THE_RECORD)
            except (KeyError, AttributeError):
                pass
        else:
            raise ValueError(_('could not identify conversation id'))

        # by default, a response always goes into a single conversation only
        broadcast_list = [(conversation_id, segments)]

        asyncio.async(
            self._begin_message_sending(broadcast_list, context, image_id=image_id, otr_status=otr_status)
        ).add_done_callback(self._on_message_sent)

    @asyncio.coroutine
    def _begin_message_sending(self, broadcast_list, context, image_id=None, otr_status=None):
        try:
            yield from self._handlers.run_pluggable_omnibus("sending", self, broadcast_list, context)
        except self.Exceptions.SuppressEventHandling:
            print(_("_begin_message_sending(): SuppressEventHandling"))
            return
        except:
            raise

        debug_sending = False
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            debug_sending = True

        if debug_sending:
            print(_("_begin_message_sending(): global context: {}").format(context))

        for response in broadcast_list:
            if debug_sending:
                print(_("_begin_message_sending(): {}").format(response[0]))

            # send messages using FakeConversation as a workaround
            _fc = FakeConversation(self._client, response[0])
            yield from _fc.send_message(response[1], image_id=image_id, otr_status=otr_status)

    def list_conversations(self):
        """List all active conversations"""
        try:
            _all_conversations = self._conv_list.get_all()
            convs = _all_conversations
            logging.info(_("list_conversations() returned {} conversation(s)").format(len(convs)))
        except Exception as e:
            logging.exception(_("list_conversations()"))
            raise

        return convs

    def get_users_in_conversation(self, conv_ids):
        """list all users in supplied conv_id(s).
        supply many conv_id as a list.
        """
        if isinstance(conv_ids, str):
            conv_ids = [conv_ids]
        all_users = []
        conv_ids = list(set(conv_ids))
        for conversation in self.list_conversations():
            for room_id in conv_ids:
                if room_id in conversation.id_:
                    all_users += conversation.users
        all_users = list(set(all_users))
        return all_users

    def get_config_option(self, option):
        return self.config.get_option(option)

    def get_config_suboption(self, conv_id, option):
        return self.config.get_suboption("conversations", conv_id, option)

    def get_memory_option(self, option):
        return self.memory.get_option(option)

    def get_memory_suboption(self, user_id, option):
        return self.memory.get_suboption("user_data", user_id, option)

    def user_memory_set(self, chat_id, keyname, keyvalue):
        self.initialise_memory(chat_id, "user_data")
        self.memory.set_by_path(["user_data", chat_id, keyname], keyvalue)
        self.memory.save()

    def user_memory_get(self, chat_id, keyname):
        value = None
        try:
            self.initialise_memory(chat_id, "user_data")
            value = self.memory.get_by_path(["user_data", chat_id, keyname])
        except KeyError:
            pass
        return value

    def conversation_memory_set(self, conv_id, keyname, keyvalue):
        self.initialise_memory(conv_id, "conv_data")
        self.memory.set_by_path(["conv_data", conv_id, keyname], keyvalue)
        self.memory.save()

    def conversation_memory_get(self, conv_id, keyname):
        value = None
        try:
            self.initialise_memory(conv_id, "conv_data")
            value = self.memory.get_by_path(["conv_data", conv_id, keyname])
        except KeyError:
            pass
        return value

    def print_conversations(self):
        print(_('Conversations:'))
        for c in self.list_conversations():
            print('  {} ({}) u:{}'.format(get_conv_name(c, truncate=True), c.id_, len(c.users)))
            for u in c.users:
                print('    {} ({}) {}'.format(u.first_name, u.full_name, u.id_.chat_id))
        print()

    def get_1on1_conversation(self, chat_id):
        """find a 1-to-1 conversation with specified user
        maintained for functionality with older plugins that do not use get_1to1()
        """
        self.initialise_memory(chat_id, "user_data")

        if self.memory.exists(["user_data", chat_id, "optout"]):
            if self.memory.get_by_path(["user_data", chat_id, "optout"]):
                return False

        conversation = None

        if self.memory.exists(["user_data", chat_id, "1on1"]):
            conversation_id = self.memory.get_by_path(["user_data", chat_id, "1on1"])
            conversation = FakeConversation(self._client, conversation_id)
            logging.info(_("memory: {} is 1on1 with {}").format(conversation_id, chat_id))
        else:
            for c in self.list_conversations():
                if len(c.users) == 2:
                    for u in c.users:
                        if u.id_.chat_id == chat_id:
                            conversation = c
                            break

            if conversation is not None:
                # remember the conversation so we don't have to do this again
                self.memory.set_by_path(["user_data", chat_id, "1on1"], conversation.id_)
                self.memory.save()

        return conversation


    @asyncio.coroutine
    def get_1to1(self, chat_id):
        """find/create a 1-to-1 conversation with specified user
        config.autocreate-1to1 = true to enable conversation creation, otherwise will revert to
            legacy behaviour of finding an existing 1-to-1
        config.bot_introduction = "some text or html" to show to users when a new conversation
            is created - "{0}" will be substituted with first bot alias
        """
        self.initialise_memory(chat_id, "user_data")

        if self.memory.exists(["user_data", chat_id, "optout"]):
            if self.memory.get_by_path(["user_data", chat_id, "optout"]):
                return False

        conversation = None

        if self.memory.exists(["user_data", chat_id, "1on1"]):
            conversation_id = self.memory.get_by_path(["user_data", chat_id, "1on1"])
            conversation = FakeConversation(self._client, conversation_id)
            logging.info("get_1on1: remembered {} for {}".format(conversation_id, chat_id))
        else:
            if self.get_config_option('autocreate-1to1'):
                """create a new 1-to-1 conversation with the designated chat id
                send an introduction message as well to the user as part of the chat creation
                """
                logging.info("get_1on1: creating 1to1 with {}".format(chat_id))
                try:
                    introduction = self.get_config_option('bot_introduction')
                    if not introduction:
                        introduction =_("<i>Hi there! I'll be using this channel to send private "
                                        "messages and alerts. "
                                        "For help, type <b>{0} help</b>. "
                                        "To keep me quiet, reply with <b>{0} opt-out</b>.</i>").format(self._handlers.bot_command[0])
                    response = yield from self._client.createconversation([chat_id])
                    new_conversation_id = response['conversation']['id']['id']
                    self.send_html_to_conversation(new_conversation_id, introduction)
                    conversation = FakeConversation(self._client, new_conversation_id)
                except Exception as e:
                    logging.exception("GET_1TO1: failed to create 1-to-1 for user {}", chat_id)
            else:
                """legacy behaviour: user must say hi to the bot first
                this creates a conversation entry in self._conv_list (even if the bot receives
                a chat invite only - a message sent on the channel auto-accepts the invite)
                """
                logging.info("get_1on1: searching for existing 1to1 with {}".format(chat_id))
                for c in self.list_conversations():
                    if len(c.users) == 2:
                        for u in c.users:
                            if u.id_.chat_id == chat_id:
                                conversation = c
                                break

            if conversation is not None:
                # remember the conversation so we don't have to do this again
                logging.info("get_1on1: determined {} for {}".format(conversation.id_, chat_id))
                self.memory.set_by_path(["user_data", chat_id, "1on1"], conversation.id_)
                self.memory.save()

        return conversation


    def initialise_memory(self, chat_id, datatype):
        if not self.memory.exists([datatype]):
            # create the datatype grouping if it does not exist
            self.memory.set_by_path([datatype], {})

        if not self.memory.exists([datatype, chat_id]):
            # create the memory
            self.memory.set_by_path([datatype, chat_id], {})

    def messagecontext(self, source, importance, tags):
        return {
            "source": source,
            "importance": importance,
            "tags": tags
        }

    def _messagecontext_legacy(self):
        return self.messagecontext("unknown", 50, ["legacy"])

    def _on_message_sent(self, future):
        """Handle showing an error if a message fails to send"""
        try:
            future.result()
        except hangups.NetworkError:
            print(_('_on_message_sent(): failed to send message'))

    @asyncio.coroutine
    def _on_connect(self, initial_data):
        """Handle connecting for the first time"""
        print(_('Connected!'))

        self._handlers = handlers.EventHandler(self)
        handlers.handler.set_bot(self) # shim for handler decorator

        try:
            # hangups-201504090500
            self._user_list = yield from hangups.user.build_user_list(
                self._client, initial_data
            )
        except AttributeError:
            # backward-compatibility: pre hangups-201504090500
            self._user_list = hangups.UserList(self._client,
                                               initial_data.self_entity,
                                               initial_data.entities,
                                               initial_data.conversation_participants)

        self._conv_list = hangups.ConversationList(self._client,
                                                   initial_data.conversation_states,
                                                   self._user_list,
                                                   initial_data.sync_timestamp)
        self._conv_list.on_event.add_observer(self._on_event)

        plugins.load(self, command)

    def _on_event(self, conv_event):
        """Handle conversation events"""

        self._execute_hook("on_event", conv_event)

        if self.get_config_option('workaround.duplicate-events'):
            if conv_event.id_ in self._cache_event_id:
                message = _("_on_event(): ignoring duplicate event {}").format(conv_event.id_)
                print(message)
                logging.warning(message)
                return
            self._cache_event_id = {k: v for k, v in self._cache_event_id.items() if v > time.time()-3}
            self._cache_event_id[conv_event.id_] = time.time()
            print("{} {}".format(conv_event.id_, conv_event.timestamp))

        event = ConversationEvent(self, conv_event)

        if isinstance(conv_event, hangups.ChatMessageEvent):
            self._execute_hook("on_chat_message", event)
            asyncio.async(self._handlers.handle_chat_message(event))

        elif isinstance(conv_event, hangups.MembershipChangeEvent):
            self._execute_hook("on_membership_change", event)
            asyncio.async(self._handlers.handle_chat_membership(event))

        elif isinstance(conv_event, hangups.RenameEvent):
            self._execute_hook("on_rename", event)
            asyncio.async(self._handlers.handle_chat_rename(event))

    def _execute_hook(self, funcname, parameters=None):
        for hook in self._hooks:
            method = getattr(hook, funcname, None)
            if method:
                try:
                    method(parameters)
                except Exception as e:
                    message = _("_execute_hooks()"), hook, e
                    print(message)
                    logging.exception(message)

    def _on_disconnect(self):
        """Handle disconnecting"""
        print(_('Connection lost!'))

    def external_send_message(self, conversation_id, text):
        """
        LEGACY
            use send_html_to_conversation()
        """
        print(_('DEPRECATED: external_send_message(), use send_html_to_conversation()'))
        self.send_html_to_conversation(conversation_id, text)

    def external_send_message_parsed(self, conversation_id, html):
        """
        LEGACY
            use send_html_to_conversation()
        """
        print(_('DEPRECATED: external_send_message_parsed(), use send_html_to_conversation()'))
        self.send_html_to_conversation(conversation_id, html)

    def send_html_to_conversation(self, conversation_id, html, context=None):
        print(_('send_html_to_conversation(): sending to {}').format(conversation_id))
        self.send_message_parsed(conversation_id, html, context)

    def send_html_to_user(self, user_id, html, context=None):
        conversation = self.get_1on1_conversation(user_id)
        if not conversation:
            print(_('send_html_to_user(): 1-to-1 conversation not found'))
            return False
        print(_('send_html_to_user(): sending to {}').format(user_id))
        self.send_message_parsed(conversation, html, context)
        return True

    def send_html_to_user_or_conversation(self, user_id_or_conversation_id, html, context=None):
        """Attempts send_html_to_user. If failed, attempts send_html_to_conversation"""
        # NOTE: Assumption that a conversation_id will never match a user_id
        if not self.send_html_to_user(user_id_or_conversation_id, html, context):
            self.send_html_to_conversation(user_id_or_conversation_id, html, context)
        print(_('DEPRECATED: send_html_to_user_or_conversation(), use send_html_to_conversation() or send_html_to_user()'))

    def user_self(self):
        myself = {
            "chat_id": None,
            "full_name": None,
            "email": None
        }
        User = self._user_list._self_user

        myself["chat_id"] = User.id_.chat_id

        if User.full_name: myself["full_name"] = User.full_name
        if User.emails and User.emails[0]: myself["email"] = User.emails[0]

        return myself


def main():
    """Main entry point"""
    # Build default paths for files.
    dirs = appdirs.AppDirs('hangupsbot', 'hangupsbot')
    default_log_path = os.path.join(dirs.user_data_dir, 'hangupsbot.log')
    default_cookies_path = os.path.join(dirs.user_data_dir, 'cookies.json')
    default_config_path = os.path.join(dirs.user_data_dir, 'config.json')
    default_memory_path = os.path.join(dirs.user_data_dir, 'memory.json')

    # Configure argument parser
    parser = argparse.ArgumentParser(prog='hangupsbot',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d', '--debug', action='store_true',
                        help=_('log detailed debugging messages'))
    parser.add_argument('--log', default=default_log_path,
                        help=_('log file path'))
    parser.add_argument('--cookies', default=default_cookies_path,
                        help=_('cookie storage path'))
    parser.add_argument('--memory', default=default_memory_path,
                        help=_('memory storage path'))
    parser.add_argument('--config', default=default_config_path,
                        help=_('config storage path'))
    parser.add_argument('--version', action='version', version='%(prog)s {}'.format(version.__version__),
                        help=_('show program\'s version number and exit'))
    args = parser.parse_args()

    # Create all necessary directories.
    for path in [args.log, args.cookies, args.config, args.memory]:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            try:
                os.makedirs(directory)
            except OSError as e:
                sys.exit(_('Failed to create directory: {}').format(e))

    # If there is no config file in user data directory, copy default one there
    if not os.path.isfile(args.config):
        try:
            shutil.copy(os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), 'config.json')),
                        args.config)
        except (OSError, IOError) as e:
            sys.exit(_('Failed to copy default config file: {}').format(e))

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(filename=args.log, level=log_level, format=LOG_FORMAT)
    # asyncio's debugging logs are VERY noisy, so adjust the log level
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    # hangups log is quite verbose too, suppress so we can debug the bot
    logging.getLogger('hangups').setLevel(logging.WARNING)

    # initialise the bot
    bot = HangupsBot(args.cookies, args.config, memory_file=args.memory)

    # start the bot
    bot.run()


if __name__ == '__main__':
    main()
