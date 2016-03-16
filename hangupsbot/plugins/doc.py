import plugins, asyncio

def _initialise(bot):
   plugins.register_user_command(["doc"])

@asyncio.coroutine
def doc(bot, event, *args):
   yield from bot.coro_send_message(event.conv,'<a href="adrress">https://goo.gl/xxxx</a>')
