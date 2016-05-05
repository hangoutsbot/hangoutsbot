"""
Spawn arbitrary commands asynchronously (as the bot user)

Stdout goes back to the main hangout
Stderr goes back to a private 1:1

We expect a "spawn" configuration dictionary in config.json.
The dictionary can appear in two places.  It -must- appear
at the main level, it -may- also appear at the per-conversation
level, but any per-conversation structure may not override
the name of the command or whether it is an admin command
or not.

    "spawn": {
        "home": "/nonstandard/home/directory",
        "commands": 
            "motd": {
                "command": ["/bin/cat", "/etc/motd"],
                "home": "/another/home/directory"
            },
            "fortune": {
                "command": ["/usr/games/fortune"]
            },
        }
    }

Any arguments passed by the user are also passed to the program.
However, those arguments are passed after a "--", so, for example:

    /bot fortune dirty

    would execute: ['/usr/games/fortune', '--',  'dirty']

Do take care with security though.  While the shell is bypassed, so no
file redirection or command chanining is allowed (e.g.  '/bot motd ;
rm -rf /' will fail), there may be unintended, such as:

    /bot motd /etc/passwd

    would execute: ['/bin/cat', '/etc/motd', '--',  '/etc/passwd']

which will still send out your password file.  If you're worried about
argument passing (and you should be), consider replacing '/bin/cat'
above with a shell script wrapper that sanitizes or ignores arguments.

While some attempt at security has been made, it's not guaranteed or
complete.  If you're running the bot as a privilged user, you get what
you deserve when you get hacked.

XXX are we initializing tags correctly?

"""

import os
import asyncio
import logging
from asyncio.subprocess import PIPE

import plugins
from commands import command

logger = logging.getLogger(__name__)

def _initialize(bot):
    bot.spawn_lock = asyncio.Lock()
    config = bot.get_config_option("spawn")
    if not config:
        return

    cmds = config.get("commands")

    # override the load logic and register our commands directly
    for cmd, info in cmds.items():
        command.register(_spawn, admin=True, final=True, name=cmd)

    logger.info("spawn - {}".format(", ".join(map(lambda cmd: "*" + cmd, list(cmds)))))
    plugins.register_admin_command(list(cmds))


def _spawn(bot, event, *args):
    """Execute a generic command"""
    config = bot.get_config_suboption(event.conv_id, "spawn")

    home_env = config["commands"][event.command_name].get("home", config.get("home"))
    if home_env:
        os.environ["HOME"] = home_env

    executable = config["commands"][event.command_name].get("command")
    if not executable:
        yield from bot.coro_send_message(event.conv_id, "Not configured")
        return

    executable = tuple(executable + ["--"] + list(args))
    proc = yield from asyncio.create_subprocess_exec(*executable, stdout=PIPE, stderr=PIPE)

    (stdout_data, stderr_data) = yield from proc.communicate()
    stdout_str = stdout_data.decode().rstrip()
    stderr_str = stderr_data.decode().rstrip()

    if len(stderr_str) > 0:
        yield from bot.coro_send_to_user_and_conversation(
            event.user.id_.chat_id, event.conv_id, stderr_str, stdout_str)
    else:
        yield from bot.coro_send_message(event.conv_id, stdout_str)
