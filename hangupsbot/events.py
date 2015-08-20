import hangups

class StatusEvent:
    """base class for all non-ConversationEvent
        TypingEvent
        WatermarkEvent
    """
    def __init__(self, bot, state_update_event):
        self.conv_event = state_update_event
        self.conv_id = state_update_event.conversation_id.id_
        self.conv = None
        self.event_id = None
        self.user_id = None
        self.user = None
        self.timestamp = None
        self.text = ''
        self.from_bot = False


class TypingEvent(StatusEvent):
    def __init__(self, bot, state_update_event):
        super().__init__(bot, state_update_event)
        self.user_id = state_update_event.user_id
        self.timestamp = state_update_event.timestamp
        self.user = bot.get_hangups_user(state_update_event.user_id)
        if self.user.is_self:
            self.from_bot = True
        self.text = "typing"


class WatermarkEvent(StatusEvent):
    def __init__(self, bot, state_update_event):
        super().__init__(bot, state_update_event)
        self.user_id = state_update_event.participant_id
        self.timestamp = state_update_event.latest_read_timestamp
        self.user = bot.get_hangups_user(state_update_event.participant_id)
        if self.user.is_self:
            self.from_bot = True
        self.text = "watermark"


class ConversationEvent(object):
    """Conversation event"""
    def __init__(self, bot, conv_event):
        self.conv_event = conv_event
        self.conv_id = conv_event.conversation_id
        self.conv = bot._conv_list.get(self.conv_id)
        self.event_id = conv_event.id_
        self.user_id = conv_event.user_id
        self.user = self.conv.get_user(self.user_id)
        self.timestamp = conv_event.timestamp
        self.text = conv_event.text.strip() if isinstance(conv_event, hangups.ChatMessageEvent) else ''

    def print_debug(self, bot=None):
        """Print informations about conversation event"""
        print('eid/dtime: {}/{}'.format(self.event_id, self.timestamp.astimezone(tz=None).strftime('%Y-%m-%d %H:%M:%S')))
        if not bot:
            # don't crash on old usage, instruct dev to supply bot
            print('cid/cname: {}/undetermined, supply parameter: bot'.format(self.conv_id))
        else:
            print('cid/cname: {}/{}'.format(self.conv_id, bot.conversations.get_name(self.conv)))
        if self.user_id.chat_id == self.user_id.gaia_id:
            print('uid/uname: {}/{}'.format(self.user_id.chat_id, self.user.full_name))
        else:
            print('uid/uname: {}!{}/{}'.format(self.user_id.chat_id, self.user_id.gaia_id, self.user.full_name))
        print('txtlen/tx: {}/{}'.format(len(self.text), self.text))
        print('eventdump: completed --8<--')
