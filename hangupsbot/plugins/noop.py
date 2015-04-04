from commands import command

@command.register
def noop(bot, event, *args):
    print("i did nothing!")