import hangups

from handlers import handler
from commands import command

@command.register(admin=True)
def noop(bot, event, *args):
    print("i did nothing!")

@handler.register(priority=5, event=hangups.ChatMessageEvent)
def _handle_nothing(bot, event):
    print("i handled nothing, but a message just went by!")