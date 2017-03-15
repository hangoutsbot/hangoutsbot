from datetime import datetime
import hangups

class MissingArgumentError(ValueError):
    pass

class FakeEvent(object):
    """Dummy Event to provide Hangups Event like access to Data around a Message

    Args:
        bot: hangupsbot instance
        conv_id: string, Conversation ID for the message
        user_id: int, Hanups User ID of the sender
        text: string, the message text
        attachments: list, urls of images for example
    """
    def __init__(self, bot, conv_id='', user_id=0, text='', attachments=None):
        if not conv_id or not user_id or not text:
            raise MissingArgumentError('missing args')
        self.bot = bot
        self.text = text

        self.conv_id = conv_id
        self.conv = bot.get_hangups_conversation(conv_id)

        self.user = bot.get_hangups_user(user_id)
        self.user_id = hangups.user.UserID(chat_id=user_id, gaia_id=user_id)
        self.from_bot = True if self.user.is_self else False

        self.timestamp = datetime.now()

        if attachments is None:
            self.attachments = []
        else:
            self.attachments = attachments

        self.event_id = 'fake_event{}'.format(self.timestamp)
