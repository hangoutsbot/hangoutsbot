import asyncio
import logging
import re
import time

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

        """
        inbuilt argument preprocessors, recognises:
        * one_chat_id (also resolves #conv)
          * @user
          * #conv|@user (tagset convuser format)
          * abcd|@user (tagset convuser format)
        * one_conv_id
          * #conv
          * #conv|* (tagset convuser format)
          * #conv|123 (tagset convuser format)
        * test cases that won't match:
          * #abcd#
          * ##abcd
          * ##abcd##
          * ##abcd|*
          * @user|abcd
          * wxyz@user
          * @user@wxyz
        """

        self.preprocessors = { "inbuilt": {
            r"^(#?[\w|]+[^#]\|)?@[\w]+[^@]$": self.one_chat_id,
            r"^#[\w|]+[^#]$": self.one_conv_id }}

        """
        disable implicit argument preprocessors on some commands
        these are special use-cases that should be rare with supplied functionality
        """
        self.preprocessors_explicit = [ "plugins.mentions.mention",
                                        "plugins.subscribe.subscribe",
                                        "plugins.subscribe.unsubscribe",
                                        "plugins.subscribe.testsubscribe" ]

    def one_chat_id(self, token, internal_context, all_users=False):
        subtokens = token.split("|", 1)

        if subtokens[0].startswith("#"):
            # probably convuser format - resolve conversation id first
            subtokens[0] = self.one_conv_id(subtokens[0], internal_context)

        text = subtokens[-1][1:]

        if text == "me":
            # current user chat_id
            subtokens[-1] = internal_context.user.id_.chat_id
        else:
            user_memory = self.bot.get_memory_option("user_data")
            if all_users:
                chat_ids = list(self.bot.conversations.catalog[internal_context.conv_id]["participants"])
            else:
                chat_ids = list(user_memory.keys())

            matched_users = {}
            for chat_id in chat_ids:
                user_data = user_memory[chat_id]
                if "_hangups" in user_data:
                    if "nickname" in user_data:
                        nickname_lower =  user_data["nickname"].lower()
                    else:
                        nickname_lower = ""
                    fullname_lower = user_data["_hangups"]["full_name"].lower()

                    if text == nickname_lower:
                        matched_users[chat_id] = chat_id
                        break

                    elif( text in fullname_lower or
                            text in fullname_lower.replace(" ", "") ):
                        matched_users[chat_id] = chat_id

            if len(matched_users) == 1:
                subtokens[-1] = list(matched_users)[0]
            elif len(matched_users) == 0:
                if not all_users:
                    # redo the user search, expanded to all users
                    # since this is calling itself again, completely overwrite subtokens
                    subtokens = self.one_chat_id(
                        token,
                        internal_context,
                        all_users=True ).split("|", 1)
                else:
                    raise ValueError("{} returned no users".format(token))
            else:
                raise ValueError("{} returned more than one user".format(token))

        return "|".join(subtokens)

    def one_conv_id(self, token, internal_context):
        subtokens = token.split("|", 1)

        text = subtokens[0][1:]
        if text == "here":
            # current conversation id
            subtokens[0] = internal_context.conv_id
        else:
            filter = "(type:GROUP)and(text:{})".format(text)
            conv_list = self.bot.conversations.get(filter)
            if len(conv_list) == 1:
                subtokens[0] = next(iter(conv_list))
            elif len(conv_list) == 0:
                raise ValueError("{} returned no conversations".format(token))
            else:
                raise ValueError("{} returned too many conversations".format(token))

        return "|".join(subtokens)

    def preprocess_arguments(self, args, internal_context, force_trigger="", force_groups=[]):
        """custom preprocessing for use by other plugins, specify:
        * force_trigger word to override config, default
          prevents confusion if botmin has overridden this for their own usage
        * force_groups to a list of resolver group names
          at least 1 must exist, otherwise all resolvers will be used (as usual)"""

        all_groups = list(self.preprocessors.keys())
        force_groups = [ g for g in force_groups if g in all_groups ]
        all_groups = force_groups or all_groups

        _implicit = ( bool(force_groups)
                        or not self.bot.get_config_option("commands.preprocessor.explicit") )
        _trigger = ( force_trigger
                        or self.bot.get_config_option("commands.preprocessor.trigger")
                        or "resolve" ).lower()

        _trigger_on = "+" + _trigger
        _trigger_off = "-" + _trigger
        _separator = ":"

        if internal_context.command_path in self.preprocessors_explicit and _implicit:
            _implicit = False

        """
        simple finite state machine parser:

        * arguments are processed in order of input, from left-to-right
        * default setting is always post-process
          * switch off with config.json: commands.preprocessor.explicit = true
        * default base trigger keyword = "resolve"
          * override with config.json: commands.preprocessor.trigger
          * full trigger keywords are:
            * +<trigger> (add)
            * -<trigger> (remove)
          * customised trigger word must be unique enough to prevent conflicts for other plugin parameters
          * all examples here assume the trigger keyword is the default
          * devs: if conflict arises, other plugins have higher priority than this
        * activate all resolvers for subsequent keywords (not required if implicit):
            +resolve
        * deactivate all resolvers for subsequent keywords:
            -resolve
        * activate specific resolver groups via keyword:
            +resolve:<comma-separated list of resolver groups, no spaces> e.g.
            +resolve:inbuilt,customalias1,customalias2
        * deactivate all active resolvers via keyword:
            +resolve:off
            +resolve:false
            +resolve:0
        * deactivate specific resolvers via keyword:
            -resolve:inbuilt
            -resolve:inbuilt,customa
        * escape trigger keyword with:
          * quotes
              "+resolve"
          * backslash
              \+resolve
        """

        if "inbuilt" in all_groups:
            # lowest priority: inbuilt
            all_groups.remove("inbuilt")
            all_groups.append("inbuilt")

        if _implicit:
            # always-on
            default_groups = all_groups
        else:
            # on-demand
            default_groups = []

        apply_resolvers = default_groups
        new_args = []
        for arg in args:
            arg_lower = arg.lower()
            skip_arg = False
            if _trigger_on == arg_lower:
                # explicitly turn on all resolvers
                #   +resolve
                apply_resolvers = all_groups
                skip_arg = True
            elif _trigger_off == arg_lower:
                # explicitly turn off all resolvers
                #   -resolve
                apply_resolvers = []
                skip_arg = True
            elif arg_lower.startswith(_trigger_on + _separator):
                _right = arg_lower.split(_separator, 1)[-1]
                if not _right or _right in ("off", "false", "0"):
                    # turn off all resolver groups
                    #   +resolve:off
                    #   +resolve:false
                    #   +resolve:0
                    #   +resolve:
                    apply_resolvers = []
                elif _right == "*":
                    # turn on all resolver groups
                    #   +resolve:*
                    apply_resolvers = all_groups
                else:
                    # turn on specific resolver groups
                    #   +resolve:inbuilt
                    #   +resolve:inbuilt,customa,customb
                    apply_resolvers = _right.split(",")
                skip_arg = True
            elif arg_lower.startswith(_trigger_off + _separator):
                _right = arg_lower.split(_separator, 1)[-1]
                if not _right or _right in ("*"):
                    # turn off all resolver groups
                    #   -resolve:*
                    #   -resolve:
                    apply_resolvers = []
                else:
                    # turn off specific groups:
                    #   -resolve:inbuilt
                    #   -resolve:customa,customb
                    for _group in _right.split(","):
                        apply_resolvers.remove(_group)
                skip_arg = True
            if skip_arg:
                # never consume the trigger term
                continue
            for rname in [ rname
                          for rname in apply_resolvers
                          if rname in all_groups ]:
                for pattern, callee in self.preprocessors[rname].items():
                    if re.match(pattern, arg, flags=re.IGNORECASE):
                        try:
                            _arg = callee(arg, internal_context)
                            if _arg:
                                arg = _arg
                                continue
                        except Exception as e:
                            raise
            new_args.append(arg)

        return new_args

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

        """default: if exceptions occur in a command, output as message
        supply keyword argument raise_exceptions=True to override behaviour"""
        raise_exceptions = False
        if "raise_exceptions" in kwds:
            raise_exceptions = kwds["raise_exceptions"]
            del kwds["raise_exceptions"]

        setattr(event, 'command_name', command_name)
        setattr(event, 'command_module', func.__module__ )
        setattr(event, 'command_path', func.__module__ + '.' + command_name)

        try:
            args = list(args[1:])
            args = self.preprocess_arguments(args, internal_context=event)
            results = yield from func(bot, event, *args, **kwds)
            return results

        except Exception as e:
            if raise_exceptions:
                raise

            logger.exception("RUN: {}".format(func.__name__))
            yield from self.bot.coro_send_message(
                event.conv,
                "<b><pre>{0}</pre></b> <pre>{1}</pre>: <em><pre>{2}</pre></em>".format(
                    func.__name__, type(e).__name__, str(e)) )

    def register(self, *args, admin=False, tags=None, final=False, name=None):
        """Decorator for registering command"""

        def wrapper(func):
            func_name = name or func.__name__

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

    def register_argument_preprocessor_group(self, name, preprocessors):
        name_lower = name.lower()
        self.preprocessors[name_lower] = preprocessors
        plugins.tracking.register_command_argument_preprocessors_group(name_lower)

# CommandDispatcher singleton
command = CommandDispatcher()
