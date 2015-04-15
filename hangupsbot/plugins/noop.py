from commands import command

@command.register(admin=True)
def noop(bot, event, *args):
    print("i did nothing!")