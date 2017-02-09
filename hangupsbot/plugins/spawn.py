"""
Spawn arbitrary commands asynchronously (as the bot user)

Stdout goes back to the main hangout
Stderr goes back to a private 1:1

We expect a "spawn" configuration dictionary in config.json.  The
dictionary can appear in two places.  It -must- appear at the main
level, it -may- also appear at the per-conversation level, but any
per-conversation structure may not override the name of the command or
whether it is an admin command or not.

    "spawn": {
        "home": "/nonstandard/home/directory",
        "commands":
            "fortune": {
                "command": ["/usr/games/fortune"]
            },
            "motd": {    <---this is a deliberately unsecure example
                "command": ["/bin/cat", "/etc/motd", "--"],
                "allow_args": true
            },
            "stock-info": {
                "command": ["/home/portfolio/stock-info", "--"]
                "home": "/home/portfolio",
                "allow_args": true
        }
    }

Security notes:

While some attempt at security has been made, it's neither guaranteed or
complete.  If you're running the bot as a privlieged user, you get what
you deserve when you get hacked, and we will all laugh at you when you
share your sad story.

If `allow_args` has been set to true, any arguments passed in by the user
are also passed to the program.  *Use this with caution*, and also consider
ending your commands with '--' to avoid allowing users to masqurade
arguments as options, should that be an issue for a particular command.

While the shell is bypassed, so no file redirection or command chanining
is allowed (e.g. `/bot motd ; rm -rf /` will fail), if `allow_args` is
true, you are passing unsanitised arguments off to a command.  Even if,
as in the `motd` example above, where the command has '--' as part of it,
so that the user cannot pass in any additional switch based arguments,
unintended consequences can occur:

    /bot motd /etc/passwd

would execute:

    ['/bin/cat', '/etc/motd', '--',  '/etc/passwd']

which will, of course, send back `/etc/passwd`.

You're responsible for sanitizing any arguments passed on to the
program, if `allow_args` is true. Writing your own small shell
script to do so may be your best option.

The environment variables from this program are passed along to
the subprocess, along with additional helpers (see code below).
"""

import os
import logging
import asyncio
from asyncio.subprocess import PIPE

from commands import command
import plugins

logger = logging.getLogger(__name__)

def _initialize(bot):
    bot.spawn_lock = asyncio.Lock()
    config = bot.get_config_option("spawn")
    if not config:
        return

    cmds = config.get("commands")

    # override the load logic and register our commands directly
    for cmd in cmds:
        command.register(_spawn, admin=True, final=True, name=cmd)

    logger.info("spawn - %s", ", ".join(['*' + cmd for cmd in cmds]))
    plugins.register_admin_command(list(cmds))


def _spawn(bot, event, *args):
    """Execute a generic command"""
    config = bot.get_config_suboption(event.conv_id, "spawn")
    cmd_config = config["commands"][event.command_name.lower()]

    home_env = cmd_config.get("home", config.get("home"))
    if home_env:
        os.environ["HOME"] = home_env

    executable = cmd_config.get("command")
    if not executable:
        yield from bot.coro_send_message(event.conv_id, "Not configured")
        return

    if cmd_config.get("allow_args"):
        executable = executable + list(args)

    executable = tuple(executable)
    logger.info("%s executing: %s", event.user.full_name, executable)

    environment = {
        'HANGOUT_USER_CHATID': event.user_id.chat_id,
        'HANGOUT_USER_FULLNAME': event.user.full_name,
        'HANGOUT_CONV_ID':  event.conv_id,
        'HANGOUT_CONV_TAGS': ','.join(bot.tags.useractive(event.user_id.chat_id,
                                                          event.conv_id))
    }
    environment.update(dict(os.environ))

    proc = yield from asyncio.create_subprocess_exec(*executable, stdout=PIPE, stderr=PIPE,
                                                     env=environment)

    (stdout_data, stderr_data) = yield from proc.communicate()
    stdout_str = stdout_data.decode().rstrip()
    stderr_str = stderr_data.decode().rstrip()

    if len(stderr_str) > 0:
        yield from bot.coro_send_to_user_and_conversation(
            event.user.id_.chat_id, event.conv_id, stderr_str, stdout_str)
    else:
        yield from bot.coro_send_message(event.conv_id, stdout_str)
