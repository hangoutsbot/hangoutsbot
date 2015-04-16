from commands import command

@command.register(admin=True)
def noop_nested(bot, event, *args):
    print("nested: i did nothing!")