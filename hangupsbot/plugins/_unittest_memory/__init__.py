"""memory unit test
all these commands work on memory.json
* creating, updating, removing a string in memory["unittest"] (memory test)
* creating, updating, removing a string in memory["unittest"]["timestamp"] (submemory test)
* retrieving and setting taint status of memory
"""

import time

def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["memorytaint", "memoryuntaint", "memorystatus", "memoryset", "memoryget", "memorypop", "memorysave", "submemoryinit", "submemoryclear", "submemoryset", "submemoryget", "submemorypop", "submemorydelete", "memorydelete"])
    return []

def memoryset(bot, event, *args):
    timestamp = time.time()
    bot.memory["unittest"] = str(timestamp)
    print("memoryset(): {}".format(timestamp))

def memoryget(bot, event, *args):
    print("memoryget(): {}".format(bot.memory["unittest"]))

def memorypop(bot, event, *args):
    the_string = bot.memory.pop("unittest")
    print("memorypop(): {}".format(the_string))

def memorytaint(bot, event, *args):
    if bot.memory.changed:
        print("memorytaint(): memory already tainted")
    else:
        bot.memory.force_taint()
        print("memorytaint(): memory tainted")

def memoryuntaint(bot, event, *args):
    if bot.memory.changed:
        bot.memory.changed = False
        print("memoryuntaint(): memory de-tainted")
    else:
        print("memoryuntaint(): memory not tainted")

def memorystatus(bot, event, *args):
    if bot.memory.changed:
        print("memorystatus(): memory tainted")
    else:
        print("memorystatus(): memory not tainted")

def memorysave(bot, event, *args):
    bot.memory.save() 

def submemoryinit(bot, event, *args):
    bot.memory["unittest-submemory"] = {}

def submemoryclear(bot, event, *args):
    bot.memory.pop("unittest-submemory")

def submemoryset(bot, event, *args):
    timestamp = time.time()
    bot.memory["unittest-submemory"]["timestamp"] = str(timestamp)
    print("submemoryset(): {}".format(timestamp))

def submemoryget(bot, event, *args):
    print("submemoryget(): {}".format(bot.memory["unittest-submemory"]["timestamp"]))

def submemorypop(bot, event, *args):
    the_string = bot.memory["unittest-submemory"].pop("timestamp")
    print("submemorypop(): {}".format(the_string))

def memorydelete(bot, event, *args):
    the_string = bot.memory.pop_by_path(["unittest"])
    print("memorydelete(): {}".format(the_string))

def submemorydelete(bot, event, *args):
    the_string = bot.memory.pop_by_path(["unittest-submemory", "timestamp"])
    print("submemorydelete(): {}".format(the_string))
