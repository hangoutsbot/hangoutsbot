#!/usr/bin/env python
import os, sys, time, datetime, random, argparse, logging
import unicodedata, collections, functools, shlex, json

import appdirs
from tornado import ioloop, gen

import hangups
from hangups.utils import get_conv_name


__version__ = '1.0'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def word_in_text(word, text):
    """Return True if word is in text"""
    # Transliterate unicode characters to ASCII and make everything lowercase
    word = unicodedata.normalize('NFKD', word).encode('ascii', 'ignore').decode().lower()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()

    # Replace delimiters in text with whitespace
    for delim in '.,:;!?':
        text = text.replace(delim, ' ')

    return True if word in text.split() else False

def text_to_segments(text):
    """Create list of message segments from text"""
    # Replace two consecutive spaces with space and non-breakable space,
    # then split text to lines
    lines = text.replace('  ', ' \xa0').splitlines()
    if not lines:
        return []

    # Generate line segments
    segments = []
    for line in lines[:-1]:
        if line:
            segments.append(hangups.ChatMessageSegment(line))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    if lines[-1]:
        segments.append(hangups.ChatMessageSegment(lines[-1]))

    return segments

class Config(collections.MutableMapping):
    """Configuration JSON storage class"""
    def __init__(self, filename, default=None):
        self.filename = filename
        self.default = None
        self.config = {}
        self.changed = False
        self.load()

    def load(self):
        """Load config from file"""
        try:
            self.config = json.load(open(self.filename))
        except IOError:
            self.config = {}
        self.changed = False

    def loads(self, json_str):
        """Load config from JSON string"""
        self.config = json.loads(json_str)
        self.changed = True

    def save(self):
        """Save config to file (only if config has changed)"""
        if self.changed:
            with open(self.filename, 'w') as f:
                json.dump(self.config, f, indent=2, sort_keys=True)
                self.changed = False

    def get_by_path(self, keys_list):
        """Get item from config by path (list of keys)"""
        return functools.reduce(lambda d, k: d[k], keys_list, self)

    def set_by_path(self, keys_list, value):
        """Set item in config by path (list of keys)"""
        self.get_by_path(keys_list[:-1])[keys_list[-1]] = value

    def __getitem__(self, key):
        try:
            return self.config[key]
        except KeyError:
            return self.default

    def __setitem__(self, key, value):
        self.config[key] = value
        self.changed = True

    def __delitem__(self, key):
        del self.config[key]
        self.changed = True

    def __iter__(self):
        return iter(self.config)

    def __len__(self):
        return len(self.config)


class CommandDispatcher(object):
    """Register commands and run them"""
    def __init__(self):
        self.commands = {}
        self.unknown_command_func = None

    @gen.coroutine
    def run(self, *args, instance=None, **kwds):
        """Run command"""
        try:
            func = self.commands[args[0]]
        except KeyError:
            if self.unknown_command_func:
                func = self.unknown_command_func
            else:
                raise

        args = list(args[1:])
        if instance:
            args.insert(0, instance)

        try:
            yield func(*args, **kwds)
        except Exception as e:
            print(e)

    def register(self, func):
        """Decorator for registering command"""
        self.commands[func.__name__] = func
        return func

    def register_unknown(self, func):
        """Decorator for registering unknown command"""
        self.unknown_command_func = func
        return func


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


class MessageHandler(object):
    """Handle Hangups conversation events"""
    command = CommandDispatcher()

    def __init__(self, bot):
        self.bot = bot

    @gen.coroutine
    def handle(self, event):
        """Handle conversation event"""
        if logging.root.level == logging.DEBUG:
            event.print_debug()

        if not event.user.is_self and event.text:
            if event.text.split()[0].lower() == '/bot':
                # Run command
                yield self.handle_command(event)
            else:
                # Forward messages
                yield self.handle_forward(event)

                # Send automatic replies
                yield self.handle_autoreply(event)

    @gen.coroutine
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
                                  '{}: Co si bude pán ráčit?'.format(event.user.full_name))
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
        yield self.command.run(*line_args[1:], instance=self, event=event)

    @gen.coroutine
    def handle_forward(self, event):
        """Handle message forwarding"""
        # Test if message forwarding is enabled
        if not self.bot.get_config_suboption(event.conv_id, 'forwarding_enabled'):
            return

        forward_to_list = self.bot.get_config_suboption(event.conv_id, 'forward_to')
        if forward_to_list:
            for dst in forward_to_list:
                # Prepend forwarded message with name of sender
                segments = [hangups.ChatMessageSegment('{}: '.format(event.user.full_name), is_bold=True)]
                # Copy original message segments
                segments.extend(event.conv_event.segments)
                # Append links to attachments (G+ photos) to forwarded message
                if event.conv_event.attachments:
                    segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
                    segments.extend([hangups.ChatMessageSegment(link, hangups.SegmentType.LINK, link_target=link)
                                     for link in event.conv_event.attachments])
                self.bot.send_message_segments(self.bot._conv_list.get(dst), segments)

    @gen.coroutine
    def handle_autoreply(self, event):
        """Handle autoreplies to keywords in messages"""
        # Test if autoreplies are enabled
        if not self.bot.get_config_suboption(event.conv_id, 'autoreplies_enabled'):
            return

        autoreplies_list = self.bot.get_config_suboption(event.conv_id, 'autoreplies')
        if autoreplies_list:
            for kwds, sentence in autoreplies_list:
                for kw in kwds:
                    if word_in_text(kw, event.text):
                        self.bot.send_message(event.conv, sentence)
                        break

    @command.register
    @gen.coroutine
    def help(self, command=None, *args, event=None):
        """Help me, Obi-Wan Kenobi. You're my only hope."""
        if not command:
            segments = [hangups.ChatMessageSegment('Podporované příkazy:', is_bold=True),
                        hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                        hangups.ChatMessageSegment(', '.join(sorted(self.command.commands.keys())))]
        else:
            try:
                command_fn = self.command.commands[command]
                segments = [hangups.ChatMessageSegment('{}:'.format(command), is_bold=True),
                            hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
                segments.extend(text_to_segments(command_fn.__doc__))
            except KeyError:
                yield self.unknown_command(event=event)
                return

        self.bot.send_message_segments(event.conv, segments)

    @command.register
    @gen.coroutine
    def ping(self, *args, event=None):
        """Zahrajem si ping pong!"""
        self.bot.send_message(event.conv, 'pong')

    @command.register
    @gen.coroutine
    def echo(self, *args, event=None):
        """Pojďme se opičit!"""
        self.bot.send_message(event.conv, '{}'.format(' '.join(args)))

    @command.register
    @gen.coroutine
    def users(self, *args, event=None):
        """Výpis všech uživatelů v aktuálním Hangoutu (včetně G+ účtů a emailů)"""
        segments = [hangups.ChatMessageSegment('Seznam uživatelů (celkem {}):'.format(len(event.conv.users)),
                                               is_bold=True),
                    hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
        for u in sorted(event.conv.users, key=lambda x: x.full_name.split()[-1]):
            link = 'https://plus.google.com/u/0/{}/about'.format(u.id_.chat_id)
            segments.append(hangups.ChatMessageSegment(u.full_name, hangups.SegmentType.LINK,
                                                       link_target=link))
            if u.emails:
                segments.append(hangups.ChatMessageSegment(' ('))
                segments.append(hangups.ChatMessageSegment(u.emails[0], hangups.SegmentType.LINK,
                                                           link_target='mailto:{}'.format(u.emails[0])))
                segments.append(hangups.ChatMessageSegment(')'))
            segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
        self.bot.send_message_segments(event.conv, segments)

    @command.register
    @gen.coroutine
    def hangouts(self, *args, event=None):
        """Výpis všech aktivních Hangoutů, v kterých řádí bot
           Vysvětlivky: c ... commands, f ... forwarding, a ... autoreplies"""
        segments = [hangups.ChatMessageSegment('Seznam aktivních Hangoutů:', is_bold=True),
                    hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
        for c in self.bot.list_conversations():
            s = '{} [c: {:d}, f: {:d}, a: {:d}]'.format(get_conv_name(c, truncate=True),
                                                        self.bot.get_config_suboption(c.id_, 'commands_enabled'),
                                                        self.bot.get_config_suboption(c.id_, 'forwarding_enabled'),
                                                        self.bot.get_config_suboption(c.id_, 'autoreplies_enabled'))
            segments.append(hangups.ChatMessageSegment(s))
            segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))

        self.bot.send_message_segments(event.conv, segments)

    @command.register
    @gen.coroutine
    def rename(self, *args, event=None):
        """Přejmenuje aktuální Hangout"""
        yield self.bot._client.setchatname(event.conv_id, ' '.join(args))

    @command.register
    @gen.coroutine
    def easteregg(self, easteregg, eggcount=1, period=0.5, *args, event=None):
        """Spustí combo velikonočních vajíček (parametry: vajíčko [počet] [perioda])
           Podporovaná velikonoční vajíčka: ponies, pitchforks, bikeshed, shydino"""
        for i in range(int(eggcount)):
            yield self.bot._client.sendeasteregg(event.conv_id, easteregg)
            if int(eggcount) > 1:
                yield gen.Task(ioloop.IOLoop.instance().add_timeout,
                               time.time() + int(period) + random.uniform(-0.1, 0.1))

    @command.register
    @gen.coroutine
    def spoof(self, *args, event=None):
        """Spoofne instanci IngressBota na určené koordináty"""
        segments = [hangups.ChatMessageSegment('!!! POZOR !!!', is_bold=True),
                    hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
        segments.append(hangups.ChatMessageSegment('Uživatel {} ('.format(event.user.full_name)))
        link = 'https://plus.google.com/u/0/{}/about'.format(event.user.id_.chat_id)
        segments.append(hangups.ChatMessageSegment(link, hangups.SegmentType.LINK,
                                                   link_target=link))
        segments.append(hangups.ChatMessageSegment(') byl právě reportován Nianticu za pokus o spoofing!'))
        self.bot.send_message_segments(event.conv, segments)

    @command.register
    @gen.coroutine
    def reload(self, *args, event=None):
        """Znovu načte konfiguraci bota ze souboru"""
        self.bot.config.load()

    @command.register
    @gen.coroutine
    def quit(self, *args, event=None):
        """Nech bota žít!"""
        sys.exit('HangupsBot killed by user {} from conversation {}'.format(event.user.full_name,
                                                                            get_conv_name(event.conv, truncate=True)))

    @command.register
    @gen.coroutine
    def config(self, cmd=None, *args, event=None):
        """Zobrazí nebo upraví konfiguraci bota
           Parametry: /bot config [get|set] [key] [subkey] [...] [value]"""

        if cmd == 'get' or cmd is None:
            config_args = list(args)
            value = self.bot.config.get_by_path(config_args) if config_args else dict(self.bot.config)
        elif cmd == 'set':
            config_args = list(args[:-1])
            if len(args) >= 2:
                self.bot.config.set_by_path(config_args, json.loads(args[-1]))
                self.bot.config.save()
                value = self.bot.config.get_by_path(config_args)
            else:
                yield self.unknown_command(event=event)
                return
        else:
            yield self.unknown_command(event=event)
            return

        if value is None:
            value = 'Parametr neexistuje!'

        config_path = ' '.join(k for k in ['config'] + config_args)
        segments = [hangups.ChatMessageSegment('{}:'.format(config_path),
                                                is_bold=True),
                    hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK)]
        segments.extend(text_to_segments(json.dumps(value, indent=2, sort_keys=True)))
        self.bot.send_message_segments(event.conv, segments)

    @command.register_unknown
    @gen.coroutine
    def unknown_command(self, event=None):
        """Unknown command handler"""
        self.bot.send_message(event.conv,
                              '{}: Ja ne znaju, ne ponimaju!'.format(event.user.full_name))


class HangupsBot(object):
    """Hangouts bot listening on all conversations"""
    def __init__(self, cookies_path, config_path):
        # These are populated by on_connect when it's called.
        self._conv_list = None       # hangups.ConversationList
        self._user_list = None       # hangups.UserList
        self._message_handler = None # MessageHandler

        # Load config file
        self.config = Config(config_path)

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
        ioloop.IOLoop.instance().run_sync(self._client.connect)

    def handle_chat_message(self, conv_event):
        """Handle chat messages"""
        event = ConversationEvent(self, conv_event)
        self._message_handler.handle(event)

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
        conversation.send_message(segments).add_done_callback(
            self._on_message_sent
        )

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
        self._message_handler = MessageHandler(self)

        self._user_list = hangups.UserList(initial_data.self_entity,
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

    # Start Hangups bot
    HangupsBot(args.cookies, args.config)


if __name__ == '__main__':
    main()
