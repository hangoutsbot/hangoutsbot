import hangups
from hangups.ui.utils import get_conv_name
import asyncio
import plugins

def _initialise(Handlers, bot=None):
    """
    first, you can setup stuff, initialise variables and whatever else!
    """
    plugins.register_admin_command(["lastcommand"]) 
    
    # above command is available to all users
    # Handlers.register_admin_command() if command(s) only available to admins
    return [] # always a blank list

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
