import asyncio, logging, time

import plugins


logger = logging.getLogger(__name__)


class CommandDispatcher(object):
    """Register commands and run them"""
    def __init__(self):
        self.bot = None
        self.commands = {}
        self.admin_commands = []
        self.unknown_command = None
        self.blocked_command = None
        self.tracking = None

        self.command_tagsets = {}

    def set_bot(self, bot):
        self.bot = bot

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


    def register_tags(self, command, tagsets):
        if command not in self.command_tagsets:
            self.command_tagsets[command] = set()

        if isinstance(tagsets, str):
            tagsets = set([tagsets])

        self.command_tagsets[command] = self.command_tagsets[command] | tagsets


    @property
    def deny_prefix(self):
        config_tags_deny_prefix = self.bot.get_config_option('commands.tags.deny-prefix') or "!"
        return config_tags_deny_prefix

    @property
    def escalate_tagged(self):
        config_tags_escalate = self.bot.get_config_option('commands.tags.escalate') or False
        return config_tags_escalate

    def get_available_commands(self, bot, chat_id, conv_id):
        start_time = time.time()

        config_tags_deny_prefix = self.deny_prefix
        config_tags_escalate = self.escalate_tagged

        config_admins = bot.get_config_suboption(conv_id, 'admins')
        is_admin = False
        if chat_id in config_admins:
            is_admin = True

        commands_admin = bot.get_config_suboption(conv_id, 'commands_admin') or []
        commands_user = bot.get_config_suboption(conv_id, 'commands_user') or []
        commands_tagged = bot.get_config_suboption(conv_id, 'commands_tagged') or {}

        # convert commands_tagged tag list into a set of (frozen)sets
        commands_tagged = { key: set([ frozenset(value if isinstance(value, list) else [value])
            for value in values ]) for key, values in commands_tagged.items() }
        # combine any plugin-determined tags with the config.json defined ones
        if self.command_tagsets:
            for command, tagsets in self.command_tagsets.items():
                if command not in commands_tagged:
                    commands_tagged[command] = set()
                commands_tagged[command] = commands_tagged[command] | tagsets

        all_commands = set(self.commands)

        admin_commands = set()
        user_commands = set()

        if commands_admin is True:
            """commands_admin: true # all commands are admin-only"""
            admin_commands = all_commands

        elif commands_user is True:
            """commands_user: true # all commands are user-only"""
            user_commands = all_commands

        elif commands_user:
            """commands_user: [ "command", ... ] # listed are user commands, others admin-only"""
            user_commands = set(commands_user)
            admin_commands = all_commands - user_commands

        else:
            """default: follow config["commands_admin"] + plugin settings"""
            admin_commands = set(commands_admin) | set(self.admin_commands)
            user_commands = all_commands - admin_commands

        # make admin commands unavailable to non-admin user
        if not is_admin:
            admin_commands = set()

        if commands_tagged:
            _set_user_tags = set(bot.tags.useractive(chat_id, conv_id))

            for command, tags in commands_tagged.items():
                if command not in all_commands:
                    # optimisation: don't check commands that aren't loaded into framework
                    continue

                # raise tagged command access level if escalation required
                if config_tags_escalate and command in user_commands:
                    user_commands.remove(command)

                # is tagged command generally available (in user_commands)?
                # admins always get access, other users need appropriate tag(s)
                # XXX: optimisation: check admin_commands to avoid unnecessary scanning
                if command not in user_commands|admin_commands:
                    for _match in tags:
                        _set_allow = set([_match] if isinstance(_match, str) else _match)
                        if is_admin or _set_allow <= _set_user_tags:
                            admin_commands.update([command])
                            break

            if not is_admin:
                # tagged commands can be explicitly denied
                _denied = set()
                for command in user_commands|admin_commands:
                    if command in commands_tagged:
                        tags = commands_tagged[command]
                        for _match in tags:
                            _set_allow = set([_match] if isinstance(_match, str) else _match)
                            _set_deny = { config_tags_deny_prefix + x for x in _set_allow }
                            if _set_deny <= _set_user_tags:
                                _denied.update([command])
                                break
                admin_commands = admin_commands - _denied
                user_commands = user_commands - _denied

        user_commands = user_commands - admin_commands # ensure no overlap

        interval = time.time() - start_time
        logger.debug("get_available_commands() - {}".format(interval))

        return { "admin": list(admin_commands), "user": list(user_commands) }

    @asyncio.coroutine
    def run(self, bot, event, *args, **kwds):
        """Run command"""
        command_name = args[0]
        if command_name in self.commands:
            func = self.commands[command_name]
        elif command_name.lower() in self.commands:
            func = self.commands[command_name.lower()]
        elif self.unknown_command:
            func = self.unknown_command
        else:
            raise KeyError("command {} not found".format(command_name))

        args = list(args[1:])

        try:
            results = yield from func(bot, event, *args, **kwds)
            return results

        except Exception as e:
            logger.exception("RUN: {}".format(func.__name__))
            yield from self.bot.coro_send_message(
                event.conv,
                "<b><pre>{0}</pre></b> <pre>{1}</pre>: <em><pre>{2}</pre></em>".format(
                    func.__name__, type(e).__name__, str(e)) )

    def register(self, *args, admin=False, tags=None, final=False):
        """Decorator for registering command"""

        def wrapper(func):
            func_name = func.__name__

            if final:
                # wrap command function in coroutine
                func = asyncio.coroutine(func)
                self.commands[func_name] = func
                if admin:
                    self.admin_commands.append(func_name)

            else:
                # just register and return the same function
                plugins.tracking.register_command( "admin" if admin else "user",
                                                   [func_name],
                                                   tags=tags )

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

    def register_blocked(self, func):
        """Decorator for registering unknown command"""
        self.blocked_command = asyncio.coroutine(func)
        return func

# CommandDispatcher singleton
command = CommandDispatcher()
