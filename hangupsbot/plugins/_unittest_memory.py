"""memory unit test
all these commands work on memory.json
* creating, updating, removing a string in memory["unittest"] (memory test)
* creating, updating, removing a string in memory["unittest"]["timestamp"] (submemory test)
* retrieving and setting taint status of memory
"""

import time
import logging

logger = logging.getLogger(__name__)

def _initialise(Handlers, bot=None):
    Handlers.register_admin_command(["memorytaint", "memoryuntaint", "memorystatus", "memoryset", "memoryget", "memorypop", "memorysave", "submemoryinit", "submemoryclear", "submemoryset", "submemoryget", "submemorypop", "submemorydelete", "memorydelete"])
    return []

def memoryset(bot, event, *args):
    timestamp = time.time()
    bot.memory["unittest"] = str(timestamp)
    logger.debug("memoryset(): {}".format(timestamp))

def memoryget(bot, event, *args):
    logger.debug("memoryget(): {}".format(bot.memory["unittest"]))

def memorypop(bot, event, *args):
    the_string = bot.memory.pop("unittest")
    logger.debug("memorypop(): {}".format(the_string))

def memorytaint(bot, event, *args):
    if bot.memory.changed:
        logger.debug("memorytaint(): memory already tainted")
    else:
        bot.memory.force_taint()
        logger.debug("memorytaint(): memory tainted")

def memoryuntaint(bot, event, *args):
    if bot.memory.changed:
        bot.memory.changed = False
        logger.debug("memoryuntaint(): memory de-tainted")
    else:
        logger.debug("memoryuntaint(): memory not tainted")

def memorystatus(bot, event, *args):
    if bot.memory.changed:
        logger.debug("memorystatus(): memory tainted")
    else:
        logger.debug("memorystatus(): memory not tainted")

def memorysave(bot, event, *args):
    bot.memory.save() 

def submemoryinit(bot, event, *args):
    bot.memory["unittest-submemory"] = {}

def submemoryclear(bot, event, *args):
    bot.memory.pop("unittest-submemory")

def submemoryset(bot, event, *args):
    timestamp = time.time()
    bot.memory["unittest-submemory"]["timestamp"] = str(timestamp)
    logger.debug("submemoryset(): {}".format(timestamp))

def submemoryget(bot, event, *args):
    logger.debug("submemoryget(): {}".format(bot.memory["unittest-submemory"]["timestamp"]))

def submemorypop(bot, event, *args):
    the_string = bot.memory["unittest-submemory"].pop("timestamp")
    logger.debug("submemorypop(): {}".format(the_string))

def memorydelete(bot, event, *args):
    the_string = bot.memory.pop_by_path(["unittest"])
    logger.debug("memorydelete(): {}".format(the_string))

def submemorydelete(bot, event, *args):
    the_string = bot.memory.pop_by_path(["unittest-submemory", "timestamp"])
    logger.debug("submemorydelete(): {}".format(the_string))
