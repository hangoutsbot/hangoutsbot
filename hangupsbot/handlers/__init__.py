import os, glob, logging, itertools, asyncio

import hangups
from hangups.ui.utils import get_conv_name


class StopEventHandling(Exception):
    """Raise to stop handling of current event by other handlers"""
    pass


class ConversationEvent:
    """Cenversation event wrapper"""
    def __init__(self, bot, conv_event):
        self.conv_event = conv_event
        self.conv_id = conv_event.conversation_id
        self.conv = bot._conv_list.get(self.conv_id)
        self.user_id = conv_event.user_id
        self.user = self.conv.get_user(self.user_id)
        self.timestamp = conv_event.timestamp
        self.text = conv_event.text.strip() if isinstance(conv_event, hangups.ChatMessageEvent) else ''

    def print_debug(self):
        """Print informations about conversation event"""
        print(_('Conversation ID: {}').format(self.conv_id))
        print(_('Conversation name: {}').format(get_conv_name(self.conv, truncate=True)))
        print(_('User ID: {}').format(self.user_id))
        print(_('User name: {}').format(self.user.full_name))
        print(_('Timestamp: {}').format(self.timestamp.astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')))
        print(_('Text: {}').format(self.text))
        print()


class EventHandler:
    """Register event handlers"""
    def __init__(self):
        self.handlers = []
        self.counter = itertools.count()

    def register(self, priority=10, event=None):
        """Decorator for registering event handler"""
        def wrapper(func):
            func = asyncio.coroutine(func)
            entry = (priority, next(self.counter), func, event)
            self.handlers.append(entry)
            self.handlers.sort()
            return func
        return wrapper

    @asyncio.coroutine
    def handle(self, bot, event):
        """Handle event"""
        wrapped_event = ConversationEvent(bot, event)
        if logging.root.level == logging.DEBUG:
            wrapped_event.print_debug()

        # Don't handle event if it is produced by bot
        if wrapped_event.user.is_self:
            return

        # Run all event handlers
        for prio, i, func, event_type in self.handlers:
            if event_type is None or isinstance(event, event_type):
                try:
                    yield from func(bot, wrapped_event)
                except StopEventHandling:
                    break
                except Exception as e:
                    print(e)


# Create EventHandler singleton
handler = EventHandler()

# Build list of handlers
_plugins = glob.glob(os.path.join(os.path.dirname(__file__), "*.py"))
__all__ = [os.path.splitext(os.path.basename(f))[0] for f in _plugins
           if os.path.isfile(f) and not os.path.basename(f).startswith("_")]

# Load all handlers
from hangupsbot.handlers import *
