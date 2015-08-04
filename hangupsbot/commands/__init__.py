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


    def get_available_commands(self, bot, chat_id, conv_id):
        start_time = time.time()

        config_tags_deny_prefix = bot.get_config_option('commands.tags.deny-prefix') or "!"
        config_tags_escalate = bot.get_config_option('commands.tags.escalate') or False

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

    def register(self, *args, admin=False, tags=None):
        """Decorator for registering command"""
        def wrapper(func):
            # Automatically wrap command function in coroutine
            func = asyncio.coroutine(func)
            func_name = func.__name__
            self.commands[func_name] = func

            plugins.tracking.register_command("user", [func_name], tags=tags)

            if admin:
                self.admin_commands.append(func_name)
                plugins.tracking.register_command("admin", [func_name], tags=tags)

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
