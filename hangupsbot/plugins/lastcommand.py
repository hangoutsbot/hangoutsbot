import hangups
from hangups.ui.utils import get_conv_name
import asyncio
import plugins
import shlex

from commands import command

def _initialise(Handlers, bot=None):
    """
    first, you can setup stuff, initialise variables and whatever else!
    """
    plugins.register_handler(_handle_command, "message")
    plugins.register_admin_command(["lastcommand"])
    plugins.register_user_command(["c"])

    # above command is available to all users
    # Handlers.register_admin_command() if command(s) only available to admins
    return [] # always a blank list

def _handle_command(bot, event, command):
    # Parse message
    event.text = event.text.replace(u'\xa0', u' ') # convert non-breaking space in Latin1 (ISO 8859-1)
    try:
        line_args = shlex.split(event.text, posix=False)
    except Exception as e:
        return

    if line_args[0].lower() in bot._handlers.bot_command and line_args[1].lower() != 'c':
        bot.user_memory_set(event.user.id_.chat_id, 'lastcommand', ' '.join(line_args[1:]))

def c(bot, event):
    if bot.memory.exists(["user_data", event.user.id_.chat_id, 'lastcommand']):
        lastcommand = bot.user_memory_get(event.user.id_.chat_id, 'lastcommand')
        yield from bot.coro_send_message(event.conv, '<b>Last command :<br>' + lastcommand , context={ "parser": True })
        if not lastcommand is 'c':
            yield from command.run(bot, event, *lastcommand.split())
    else:
        yield from bot.coro_send_message(event.conv, 'You have no previous command.'  , context={ "parser": True })

@asyncio.coroutine
def lastcommand(bot, event, *args):
	if not args:
		yield from bot.coro_send_message(event.conv_id, "Please provide a userid!")
		return

	userid = args[0]
	try:
		lastcommand = bot.user_memory_get(userid, 'lastcommand')
	except:
		yield from bot.coro_send_message(event.conv, '<b>No last command.<br>', context={ "parser": True })
	else:
		yield from bot.coro_send_message(event.conv, '<b>Last command for ' + userid + ' :<br>' + lastcommand , context={ "parser": True })
	finally:
		pass
