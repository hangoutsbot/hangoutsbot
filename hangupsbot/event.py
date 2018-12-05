import logging

import hangups


logger = logging.getLogger(__name__)


class GenericEvent:
    bot = None
    emit_log = logging.INFO

    def __init__(self, bot):
        self.bot = bot


class StatusEvent(GenericEvent):
    """base class for all non-ConversationEvent"""

    def __init__(self, bot, state_update_event):
        super().__init__(bot)

        self.conv_event = state_update_event
        self.conv_id = state_update_event.conversation_id.id
        self.conv = None
        self.event_id = None
        self.user_id = None
        self.user = None
        self.timestamp = None
        self.text = ''
        self.from_bot = False


class TypingEvent(StatusEvent):
    """user starts/pauses/stops typing"""

    def __init__(self, bot, state_update_event):
        super().__init__(bot, state_update_event)

        self.conv_event = hangups.parsers.parse_typing_status_message(state_update_event)

        self.user_id = state_update_event.sender_id
        self.timestamp = state_update_event.timestamp
        self.user = self.bot.get_hangups_user(state_update_event.sender_id)
        if self.user.is_self:
            self.from_bot = True
        self.text = "typing"


class WatermarkEvent(StatusEvent):
    """user reads up to a certain point in the conversation"""

    def __init__(self, bot, state_update_event):
        super().__init__(bot, state_update_event)

        self.conv_event =  hangups.parsers.parse_watermark_notification(state_update_event)

        self.user_id = state_update_event.sender_id
        self.timestamp = state_update_event.latest_read_timestamp
        self.user = self.bot.get_hangups_user(state_update_event.sender_id)
        if self.user.is_self:
            self.from_bot = True
        self.text = "watermark"


class ConversationEvent(GenericEvent):
    """user joins, leaves, renames or messages a conversation"""

    def __init__(self, bot, conv_event):
        super().__init__(bot)

        self.conv_event = conv_event
        self.conv_id = conv_event.conversation_id
        self.conv = self.bot._conv_list.get(self.conv_id)
        self.event_id = conv_event.id_
        self.user_id = conv_event.user_id
        self.user = self.conv.get_user(self.user_id)
        self.timestamp = conv_event.timestamp
        self.text = conv_event.text.strip() if isinstance(conv_event, hangups.ChatMessageEvent) else ''

        self.log()


    def log(self):
        if logger.isEnabledFor(self.emit_log):
            logger.log(self.emit_log, 'eid/dt: {}/{}'.format(self.event_id, self.timestamp.astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')))
            logger.log(self.emit_log, 'cid/cn: {}/{}'.format(self.conv_id, self.bot.conversations.get_name(self.conv)))
            logger.log(self.emit_log, 'c/g/un: {}/{}/{}'.format(self.user_id.chat_id, self.user_id.gaia_id, self.user.full_name))
            logger.log(self.emit_log, 'len/tx: {}/{}'.format(len(self.text), self.text))
