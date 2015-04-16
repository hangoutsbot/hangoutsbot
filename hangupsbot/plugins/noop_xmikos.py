import hangups
from handlers import handler
from commands import command

@command.register(admin=True)
def noop_xmikos(bot, event, *args):
    print("xmikosbot: i did nothing!")

@handler.register(priority=5, event=hangups.ChatMessageEvent)
def _handle_nothing_xmikos(bot, event):
    print("xmikosbot: i handled nothing, but a message just went by!")