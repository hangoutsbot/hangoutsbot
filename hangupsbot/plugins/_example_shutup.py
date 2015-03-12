"""
example plugin demonstrating various levels of sending handler suppression 
"""

def _initialise(Handlers, bot=None):
    Handlers.register_handler(_shutup, type="sending", priority=49)

def _shutup(bot, event, command):
    # raise bot.Exceptions.SuppressHandler() # suppresses this specific handler only
    # raise bot.Exceptions.SuppressAllHandlers() # disables all handlers of priority > 49
    raise bot.Exceptions.SuppressEventHandling() # disables sending entirely