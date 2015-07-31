import sys, json, asyncio, logging, os

import hangups

from version import __version__
from utils import text_to_segments

import plugins


logger = logging.getLogger(__name__)


class CommandDispatcher(object):
    """Register commands and run them"""
    def __init__(self):
        self.commands = {}
        self.admin_commands = []
        self.unknown_command = None
        self.tracking = None

    def set_tracking(self, tracking):
        self.tracking = tracking

    def get_admin_commands(self, bot, conv_id):
        logger.warning("[DEPRECATED] command.get_admin_commands(), use command.get_available_commands() instead")
        """Get list of admin-only commands (set by plugins or in config.json)
        list of commands is determined via one of two methods:
            default mode allows individual plugins to make the determination for admin and user
              commands, user commands can be "promoted" to admin commands via config.json:commands_admin
            override this behaviour by defining config.json:commands_user, which will only allow
              commands which are explicitly defined in this config key to be executed by users.
              note: overriding default behaviour makes all commands admin-only by default
        """
        whitelisted_commands = bot.get_config_suboption(conv_id, 'commands_user') or []
        if whitelisted_commands:
            admin_command_list = self.commands.keys() - whitelisted_commands
        else:
            commands_admin = bot.get_config_suboption(conv_id, 'commands_admin') or []
            admin_command_list = commands_admin + self.admin_commands
        return list(set(admin_command_list))

    def get_available_commands(self, bot, chat_id, conv_id):
        commands_admin = bot.get_config_suboption(conv_id, 'commands_admin') or []
        commands_user = bot.get_config_suboption(conv_id, 'commands_user') or []

        commands_tagged = bot.get_config_suboption(conv_id, 'commands_tagged') or {}

        # XXX: DEBUG
        commands_tagged = { "whereami" : [ "run-whereami" ],
                            "version" : [ "run-version", [ "run-version-part-1", "run-version-part-2" ] ],
                            "screenshot" : [ "run-screenshot" ] }

        admin_commands = []
        user_commands = []

        if commands_admin is True:
            """commands_admin: true
            all commands admin-only"""
            admin_commands = self.commands.keys()
            user_commands = []

        elif commands_user is True:
            """commands_user: true
            all commands user-only"""
            admin_commands = []
            user_commands = self.commands.keys()

        elif commands_user:
            """commands_user: [ "command", ... ]
            explicit user commands, everything else admin-only"""
            admin_commands = self.commands.keys() - commands_user
            user_commands = commands_user

        else:
            """default
            follow config["commands_admin"] + plugin settings"""
            admin_commands = commands_admin + self.admin_commands
            user_commands = self.commands.keys() - admin_commands

        # make admin commands unavailable to non-admin user
        admins_list = bot.get_config_suboption(conv_id, 'admins')
        if chat_id not in admins_list:
            admin_commands = []

        if commands_tagged:
            _set_user_tags = set(bot.tags.useractive(chat_id, conv_id))

            for command, tags in commands_tagged.items():
                if command in user_commands:
                    # make command admin-level
                    user_commands.remove(command)

                # make command available if user has matching tags
                for _match in tags:
                    if set([_match] if isinstance(_match, str) else _match) <= _set_user_tags:
                        admin_commands.append(command)
                        break

        admin_commands = list(set(admin_commands))
        user_commands = list(set(user_commands))

        return { "admin": admin_commands, "user": user_commands }

    @asyncio.coroutine
    def run(self, bot, event, *args, **kwds):
        """Run command"""
        try:
            func = self.commands[args[0]]
        except KeyError:
            if self.unknown_command:
                func = self.unknown_command
            else:
                raise

        args = list(args[1:])

        try:
            yield from func(bot, event, *args, **kwds)
        except Exception as e:
            message = "CommandDispatcher.run: {}".format(func.__name__)
            print("EXCEPTION in {}".format(message))
            logger.exception(message)

    def register(self, *args, admin=False):
        """Decorator for registering command"""
        def wrapper(func):
            # Automatically wrap command function in coroutine
            func = asyncio.coroutine(func)
            self.commands[func.__name__] = func
            if self.tracking:
                plugins.tracking.register_command("user", [func.__name__])
            if admin:
                self.admin_commands.append(func.__name__)
                if self.tracking:
                    plugins.tracking.register_command("admin", [func.__name__])
            return func

        # If there is one (and only one) positional argument and this argument is callable,
        # assume it is the decorator (without any optional keyword arguments)
        if len(args) == 1 and callable(args[0]):
            return wrapper(args[0])
        else:
            return wrapper

    def register_unknown(self, func):
        """Decorator for registering unknown command"""
        self.unknown_command = asyncio.coroutine(func)
        return func


# CommandDispatcher singleton
command = CommandDispatcher()

@command.register
def help(bot, event, cmd=None, *args):
    """list supported commands, /bot help <command> will show additional details"""
    help_lines = []
    link_to_guide = bot.get_config_suboption(event.conv_id, 'link_to_guide')
    if not cmd:
        admins_list = bot.get_config_suboption(event.conv_id, 'admins')

        commands = command.get_available_commands(bot, event.user.id_.chat_id, event.conv_id)
        commands_admin = commands["admin"]
        commands_nonadmin = commands["user"]

        help_lines.append(_('<b>User commands:</b>'))
        help_lines.append(', '.join(sorted(commands_nonadmin)))

        if link_to_guide:
            help_lines.append('')
            help_lines.append(_('<i>For more information, please see: {}</i>').format(link_to_guide))

        if len(commands_admin) > 0:
            help_lines.append('')
            help_lines.append(_('<b>Admin commands:</b>'))
            help_lines.append(', '.join(sorted(commands_admin)))
    else:
        try:
            command_fn = command.commands[cmd]
            help_lines.append("<b>{}</b>: {}".format(cmd, command_fn.__doc__))
        except KeyError:
            yield from command.unknown_command(bot, event)
            return

    yield from bot.coro_send_to_user_and_conversation(
        event.user.id_.chat_id,
        event.conv_id,
        "<br />".join(help_lines), # via private message
        _("<i>{}, I've sent you some help ;)</i>") # public message
            .format(event.user.full_name))


@command.register(admin=True)
def locale(bot, event, *args):
    """set bot localisation"""
    if len(args) > 0:
        if bot.set_locale(args[0], reuse = (False if "reload" in args else True)):
            message = _("locale set to: {}".format(args[0]))
        else:
            message = _("locale unchanged")
    else:
        message = _("language code required")

    bot.send_message(event.conv, message)


@command.register
def ping(bot, event, *args):
    """reply to a ping"""
    bot.send_message(event.conv, 'pong')


@command.register
def optout(bot, event, *args):
    """toggle opt-out of bot PM"""
    optout = False
    chat_id = event.user.id_.chat_id
    bot.initialise_memory(chat_id, "user_data")
    if bot.memory.exists(["user_data", chat_id, "optout"]):
        optout = bot.memory.get_by_path(["user_data", chat_id, "optout"])
    optout = not optout

    bot.memory.set_by_path(["user_data", chat_id, "optout"], optout)
    bot.memory.save()

    if optout:
        bot.send_message_parsed(event.conv, _('<i>{}, you <b>opted-out</b> from bot private messages</i>').format(event.user.full_name))
    else:
        bot.send_message_parsed(event.conv, _('<i>{}, you <b>opted-in</b> for bot private messages</i>').format(event.user.full_name))


@command.register
def version(bot, event, *args):
    """get the version of the bot"""
    bot.send_message_parsed(event.conv, _("Bot Version: <b>{}</b>").format(__version__))


@command.register_unknown
def unknown_command(bot, event, *args):
    """handle unknown commands"""
    bot.send_message(event.conv,
                     _('{}: unknown command').format(event.user.full_name))
