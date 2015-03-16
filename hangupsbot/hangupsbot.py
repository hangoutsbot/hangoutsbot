#!/usr/bin/env python3
import os, sys, argparse, logging, shutil, asyncio, time, signal

import appdirs
import hangups
from threading import Thread

from utils import simple_parse_to_segments, class_from_name
from hangups.ui.utils import get_conv_name

import config
import handlers
from commands import command

from sinks.listener import start_listening

from inspect import getmembers, isfunction


__version__ = '2.2'
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
    def send_message(self, segments):
        yield from self._client.sendchatmessage(self.id_, [seg.serialize() for seg in segments])


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
        print('eid/dtime: {}/{}'.format(self.event_id, self.timestamp.astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')))
        print('cid/cname: {}/{}'.format(self.conv_id, get_conv_name(self.conv, truncate=True)))
        if(self.user_id.chat_id == self.user_id.gaia_id):
            print('uid/uname: {}/{}'.format(self.user_id.chat_id, self.user.full_name))
        else:
            print('uid/uname: {}!{}/{}'.format(self.user_id.chat_id, self.user_id.gaia_id, self.user.full_name))
        print('txtlen/tx: {}/{}'.format(len(self.text), self.text))
        print('eventdump: completed --8<--')


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
            print("HangupsBot: memory file will be used: {}".format(memory_file))
            self.memory = config.Config(memory_file)
            if not os.path.isfile(memory_file):
                try:
                    print("creating memory file: {}".format(memory_file))
                    self.memory.force_taint()
                    self.memory.save()
                except (OSError, IOError) as e:
                    sys.exit('failed to create default memory file: {}'.format(e))

        # Handle signals on Unix
        # (add_signal_handler is not implemented on Windows)
        try:
            loop = asyncio.get_event_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, lambda: self.stop())
        except NotImplementedError:
            pass

    def register_shared(self, id, objectref):
        if id in self.shared:
            raise RuntimeError("{} already registered in shared".format(id))
        self.shared[id] = objectref

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
            print('Login failed ({})'.format(e))
            return False

    def run(self):
        """Connect to Hangouts and run bot"""
        cookies = self.login(self._cookies_path)
        if cookies:
            # Start asyncio event loop
            loop = asyncio.get_event_loop()

            # initialise pluggable framework
            self._load_hooks()
            self._start_sinks(loop)

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
                    logging.exception("unrecoverable low-level error")
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

    def send_message(self, conversation, text, context=None):
        """"Send simple chat message"""
        self.send_message_segments(
            conversation, 
            [hangups.ChatMessageSegment(text)], 
            context)

    def send_message_parsed(self, conversation, html, context=None):
        segments = simple_parse_to_segments(html)
        self.send_message_segments(conversation, segments, context)

    def send_message_segments(self, conversation, segments, context=None):
        """Send chat message segments"""
        # Ignore if the user hasn't typed a message.
        if len(segments) == 0:
            return

        # add default context if none exists
        if not context:
            context = {}
        context["base"] = self._messagecontext_legacy()

        # reduce conversation to the only thing we need: the id
        if isinstance(conversation, (FakeConversation, hangups.conversation.Conversation)):
            conversation_id = conversation.id_
        elif isinstance(conversation, str):
            conversation_id = conversation
        else:
            raise ValueError('could not identify conversation id')

        # by default, a response always goes into a single conversation only
        broadcast_list = [(conversation_id, segments)]

        asyncio.async(
            self._begin_message_sending(broadcast_list, context)
        ).add_done_callback(self._on_message_sent)


    @asyncio.coroutine
    def _begin_message_sending(self, broadcast_list, context):
        try:
            yield from self._handlers.run_pluggable_omnibus("sending", self, broadcast_list, context)
        except self.Exceptions.SuppressEventHandling:
            print("_begin_message_sending(): SuppressEventHandling")
            return
        except:
            raise

        debug_sending = False
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            debug_sending = True

        if debug_sending:
            print("_begin_message_sending(): global context: {}".format(context))

        for response in broadcast_list:
            if debug_sending:
                print("_begin_message_sending(): {} {} segments(s)".format(response[0], len(response[1])))

            # send messages using FakeConversation as a workaround
            _fc = FakeConversation(self._client, response[0])
            yield from _fc.send_message(response[1])


    def list_conversations(self):
        """List all active conversations"""
        try:
            _all_conversations = self._conv_list.get_all()
            convs = _all_conversations
            logging.info("list_conversations() returned {} conversation(s)".format(len(convs)))
        except Exception as e:
            logging.exception("list_conversations()")
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
        print('Conversations:')
        for c in self.list_conversations():
            print('  {} ({}) u:{}'.format(get_conv_name(c, truncate=True), c.id_, len(c.users)))
            for u in c.users:
                print('    {} ({}) {}'.format(u.first_name, u.full_name, u.id_.chat_id))
        print()

    def get_1on1_conversation(self, chat_id):
        conversation = None

        self.initialise_memory(chat_id, "user_data")

        if self.memory.exists(["user_data", chat_id, "1on1"]):
            conversation_id = self.memory.get_by_path(["user_data", chat_id, "1on1"])
            conversation = FakeConversation(self._client, conversation_id)
            logging.info("memory: {} is 1on1 with {}".format(conversation_id, chat_id))
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

    def _load_plugins(self):
        plugin_list = self.get_config_option('plugins')
        if plugin_list is None:
            print("HangupsBot: config.plugins is not defined, using ALL")
            plugin_path = os.path.dirname(os.path.realpath(sys.argv[0])) + os.sep + "plugins"
            plugin_list = [ os.path.splitext(f)[0]  # take only base name (no extension)...
                for f in os.listdir(plugin_path)    # ...by iterating through each node in the plugin_path...
                    if os.path.isfile(os.path.join(plugin_path,f))
                        and not f.startswith(("_", ".")) # ...that does not start with _ .
                        and f.endswith(".py")] # ...and must end with .py

        for module in plugin_list:
            module_path = "plugins.{}".format(module)

            try:
                exec("import {}".format(module_path))
            except Exception as e:
                message = "{} @ {}".format(e, module_path)
                print("EXCEPTION during plugin import: " + message)
                logging.exception(message)
                continue

            print("plugin: {}".format(module))
            public_functions = [o for o in getmembers(sys.modules[module_path], isfunction)]

            candidate_commands = []

            """
            pass 1: run _initialise()/_initialize() and filter out "hidden" functions

            legacy notice: 
            older plugins will return a list of user-available functions via _initialise/_initialize().
            this LEGACY behaviour will continue to be supported. however, it is HIGHLY RECOMMENDED to
            use register_user_command(<LIST command_names>) and register_admin_command(<LIST command_names>) 
            for better security
            """
            available_commands = False # default: ALL
            try:
                self._handlers.plugin_preinit_stats((module, module_path))
                for function_name, the_function in public_functions:
                    if function_name ==  "_initialise" or function_name ==  "_initialize":
                        try:
                            _return = the_function(self._handlers, bot=self)
                        except TypeError as e:
                            # implement legacy support for plugins that don't support the bot reference
                            _return = the_function(self._handlers)
                        if type(_return) is list:
                            available_commands = _return
                    elif function_name.startswith("_"):
                        pass
                    else:
                        candidate_commands.append((function_name, the_function))
                if available_commands is False:
                    # implicit init, legacy support: assume all candidate_commands are user-available
                    self._handlers.register_user_command([function_name for function_name, function in candidate_commands])
                elif available_commands is []:
                    # explicit init, no user-available commands
                    pass
                else:
                    # explicit init, legacy support: _initialise() returned user-available commands
                    self._handlers.register_user_command(available_commands)
            except Exception as e:
                message = "{} @ {}".format(e, module_path)
                print("EXCEPTION during plugin init: " + message)
                logging.exception(message)
                continue # skip this, attempt next plugin

            """
            pass 2: register filtered functions
            """
            plugin_tracking = self._handlers.plugin_get_stats()
            explicit_admin_commands = plugin_tracking["commands"]["admin"]
            all_commands = plugin_tracking["commands"]["all"]
            registered_commands = []
            for function_name, the_function in candidate_commands:
                if function_name in all_commands:
                    command.register(the_function)
                    text_function_name = function_name
                    if function_name in explicit_admin_commands:
                        text_function_name = "*" + text_function_name
                    registered_commands.append(text_function_name)

            if registered_commands:
                print("added: {}".format(", ".join(registered_commands)))

        self._handlers.all_plugins_loaded()


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
                print("_start_sinks(): {}".format(module))
                t = Thread(target=start_listening, args=(
                  self,
                  shared_loop,
                  name,
                  port,
                  certfile,
                  class_from_name(module_name, class_name),
                  module_name))

                t.daemon = True
                t.start()

                threads.append(t)

        message = "_start_sinks(): {} sink thread(s) started".format(len(threads))
        logging.info(message)

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
                    print("_load_hooks(): {}".format(module))
                    self._hooks.append(theClass)
                else:
                    print("_load_hooks(): hook failed to initialise")

        message = "_load_hooks(): {} hook(s) loaded".format(len(self._hooks))
        logging.info(message)

    def _on_message_sent(self, future):
        """Handle showing an error if a message fails to send"""
        try:
            future.result()
        except hangups.NetworkError:
            print('_on_message_sent(): failed to send message')

    def _on_connect(self, initial_data):
        """Handle connecting for the first time"""
        print('Connected!')
        self._handlers = handlers.EventHandler(self)

        self._user_list = hangups.UserList(self._client,
                                           initial_data.self_entity,
                                           initial_data.entities,
                                           initial_data.conversation_participants)
        self._conv_list = hangups.ConversationList(self._client,
                                                   initial_data.conversation_states,
                                                   self._user_list,
                                                   initial_data.sync_timestamp)
        self._conv_list.on_event.add_observer(self._on_event)

        self._load_plugins()

    def _on_event(self, conv_event):
        """Handle conversation events"""

        self._execute_hook("on_event", conv_event)

        if self.get_config_option('workaround.duplicate-events'):
            if conv_event.id_ in self._cache_event_id:
                message = "_on_event(): ignoring duplicate event {}".format(conv_event.id_)
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
                    message = "_execute_hooks()", hook, e
                    print(message)
                    logging.exception(message)

    def _on_disconnect(self):
        """Handle disconnecting"""
        print('Connection lost!')

    def external_send_message(self, conversation_id, text):
        """
        LEGACY
            use send_html_to_conversation()
        """
        print('DEPRECATED: external_send_message(), use send_html_to_conversation()')
        self.send_html_to_conversation(conversation_id, text)

    def external_send_message_parsed(self, conversation_id, html):
        """
        LEGACY
            use send_html_to_conversation()
        """
        print('DEPRECATED: external_send_message_parsed(), use send_html_to_conversation()')
        self.send_html_to_conversation(conversation_id, html)

    def send_html_to_conversation(self, conversation_id, html, context=None):
        print('send_html_to_conversation(): sending to {}'.format(conversation_id))
        self.send_message_parsed(conversation_id, html, context)

    def send_html_to_user(self, user_id, html, context=None):
        conversation = self.get_1on1_conversation(user_id)
        if not conversation:
            print('send_html_to_user(): 1-to-1 conversation not found')
            return False
        print('send_html_to_user(): sending to {}'.format(user_id))
        self.send_message_parsed(conversation, html, context)
        return True

    def send_html_to_user_or_conversation(self, user_id_or_conversation_id, html, context=None):
        """Attempts send_html_to_user. If failed, attempts send_html_to_conversation"""
        # NOTE: Assumption that a conversation_id will never match a user_id
        if not self.send_html_to_user(user_id_or_conversation_id, html, context):
            self.send_html_to_conversation(user_id_or_conversation_id, html, context)

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
                        help='log detailed debugging messages')
    parser.add_argument('--log', default=default_log_path,
                        help='log file path')
    parser.add_argument('--cookies', default=default_cookies_path,
                        help='cookie storage path')
    parser.add_argument('--memory', default=default_memory_path,
                        help='memory storage path')
    parser.add_argument('--config', default=default_config_path,
                        help='config storage path')
    args = parser.parse_args()

    # Create all necessary directories.
    for path in [args.log, args.cookies, args.config, args.memory]:
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
    bot = HangupsBot(args.cookies, args.config, memory_file=args.memory)

    # start the bot
    bot.run()


if __name__ == '__main__':
    main()
