import asyncio, re, logging, json, random
import hangups
import plugins

logger = logging.getLogger(__name__)

def _initialise(bot):
   plugins.register_user_command(["botdoc"])
   plugins.register_admin_command(["setbotdoc"])
   
@asyncio.coroutine
def botdoc(bot, event, *args):
   """Shows the bot related documentation"""
   text = bot.user_memory_get('botdocmemory', 'botdoc')
   if text is None:
      message = u'There is no documentation for this HO bot! :(' % (event.user.full_name, name)
   else
      message = u'%s' % (text)
   yield from bot.coro_send_message(event.conv,message)

@asyncio.coroutine
def setbotdoc(bot, event, *args):
   """Set the botdoc message. Only admins can set the botdoc message. With /bot setbotdoc clear you can clear the botdoc message."""
   parameters = list(args)
   if parameters[0] == "clear":
      bot.user_memory_set('botdocmemory', 'botdoc', None)
   else: 
      bot.user_memory_set('botdocmemory', 'botdoc', ' '.join(args))
      text = bot.user_memory_get('botdocmemory', 'botdoc')
      message = u'Botdoc message stored: %s' % (text)
      yield from bot.coro_send_message(event.conv,message)
