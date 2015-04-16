from commands import command

@command.register
def nestednoop(bot, event, *args):
    print("i did nothing!")