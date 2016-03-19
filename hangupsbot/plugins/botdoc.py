import plugins, asyncio

def _initialise(bot):
   plugins.register_user_command(["botdoc"])
   plugins.register_admin_command(["setbotdoc"])

@asyncio.coroutine
def botdoc(bot, event, *args):
   yield from bot.coro_send_message(event.conv,'<a href="adrress">https://goo.gl/xxxx</a>')

@asyncio.coroutine 
def setbotdoc(bot, event, *args):
   yield from bot.coro_send_message(event.conv,'<a href="adrress">https://goo.gl/xxxx</a>')
