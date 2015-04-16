import plugins

def _initialise(bot):
    plugins.register_admin_command(["noop"])
    plugins.register_handler(_handle_nothing)

def noop(bot, event, *args):
    print("i did nothing!")

def _handle_nothing(bot, event, command):
    print("i handled nothing, but a message just went by!")