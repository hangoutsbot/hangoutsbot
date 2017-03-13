import asyncio, logging, time

from collections import namedtuple

import hangups

import hangups_shim

from utils import simple_parse_to_segments


logger = logging.getLogger(__name__)


ConversationID = namedtuple('conversation_id', ['id', 'id_'])

ClientConversation = namedtuple( 'client_conversation',
                                 [ 'conversation_id',
                                   'current_participant',
                                   'name',
                                   'otr_status',
                                   'participant_data',
                                   'read_state',
                                   'self_conversation_state',
                                    'type_' ])

ParticipantData = namedtuple( 'participant_data',
                              [ 'fallback_name',
                                'id_' ])

LastRead = namedtuple( "read_state",
                       [ 'last_read_timestamp',
                         'participant_id' ])

LatestRead = namedtuple( "self_read_state",
                         [ "latest_read_timestamp",
                           "participant_id" ])

SelfConversationState = namedtuple( 'self_conversation_state',
                                    [ 'active_timestamp',
                                      'invite_timestamp',
                                      'inviter_id',
                                      'notification_level',
                                      'self_read_state',
                                      'sort_timestamp',
                                      'status',
                                      'view' ])


class HangupsConversation(hangups.conversation.Conversation):
    bot = None

    def __init__(self, bot, conv_id):
        self.bot = bot
        self._client = bot._client

        # retrieve the conversation record from permamem
        permamem_conv = bot.conversations.catalog[conv_id]

        # retrieve the conversation record from hangups, if available
        hangups_conv = False
        if conv_id in bot._conv_list._conv_dict:
            hangups_conv = bot._conv_list._conv_dict[conv_id]._conversation

        # set some basic variables
        bot_user = bot.user_self()
        timestamp_now = int(time.time() * 1000000)

        if permamem_conv["history"]:
            otr_status = hangups_shim.schemas.OffTheRecordStatus.ON_THE_RECORD
        else:
            otr_status = hangups_shim.schemas.OffTheRecordStatus.OFF_THE_RECORD

        if permamem_conv["type"] == "GROUP":
            type_ = hangups_shim.schemas.ConversationType.GROUP
        else:
            type_ = hangups_shim.schemas.ConversationType.STICKY_ONE_TO_ONE

        current_participant = []
        participant_data = []
        read_state = []

        participants = permamem_conv["participants"][:] # use a clone
        participants.append(bot_user["chat_id"])
        participants = set(participants)
        for chat_id in participants:
            hangups_user = bot.get_hangups_user(chat_id)

            UserID = hangups.user.UserID(chat_id=hangups_user.id_.chat_id, gaia_id=hangups_user.id_.gaia_id)
            current_participant.append(UserID)

            ParticipantInfo = ParticipantData( fallback_name=hangups_user.full_name,
                                               id_=UserID )

            participant_data.append(ParticipantInfo)

            if not hangups_conv:
                read_state.append( LastRead( last_read_timestamp=0,
                                             participant_id=UserID ))

        active_timestamp = timestamp_now
        invite_timestamp = timestamp_now
        inviter_id = hangups.user.UserID( chat_id=bot_user["chat_id"],
                                          gaia_id=bot_user["chat_id"] )
        latest_read_timestamp = timestamp_now
        sort_timestamp = timestamp_now

        if hangups_conv:
            read_state = hangups_conv.read_state[:]
            active_timestamp = hangups_conv.self_conversation_state.active_timestamp
            invite_timestamp = hangups_conv.self_conversation_state.invite_timestamp
            inviter_id = hangups_conv.self_conversation_state.inviter_id
            latest_read_timestamp = hangups_conv.self_conversation_state.self_read_state.latest_read_timestamp
            sort_timestamp = hangups_conv.self_conversation_state.sort_timestamp
            logger.debug("properties cloned from hangups conversation")

        conversation_id = ConversationID( id = conv_id,
                                          id_ = conv_id )

        self_conversation_state = SelfConversationState( active_timestamp=timestamp_now,
                                                         invite_timestamp=timestamp_now,
                                                         inviter_id=hangups.user.UserID( chat_id=bot_user["chat_id"],
                                                                                         gaia_id=bot_user["chat_id"] ),
                                                         notification_level=hangups_shim.schemas.ClientNotificationLevel.RING,
                                                         self_read_state=LatestRead( latest_read_timestamp=latest_read_timestamp,
                                                                                     participant_id=hangups.user.UserID( chat_id=bot_user["chat_id"],
                                                                                                                         gaia_id=bot_user["chat_id"] )),
                                                         sort_timestamp=sort_timestamp,
                                                         status=hangups_shim.schemas.ClientConversationStatus.ACTIVE,
                                                         view=hangups_shim.schemas.ClientConversationView.INBOX_VIEW )

        self._conversation = ClientConversation( conversation_id=conversation_id,
                                                 current_participant=current_participant,
                                                 name=permamem_conv["title"],
                                                 otr_status=otr_status,
                                                 participant_data=participant_data,
                                                 read_state=read_state,
                                                 self_conversation_state=self_conversation_state,
                                                 type_=type_ )

        # initialise blank
        self._user_list = []
        self._events = []
        self._events_dict = {}
        self._send_message_lock = asyncio.Lock()

    @property
    def users(self):
        return [ self.bot.get_hangups_user(part.id_.chat_id) for part in self._conversation.participant_data ]


class FakeConversation(object):
    def __init__(self, bot, id_):
        self.bot = bot
        self._client = self.bot._client
        self.id_ = id_

    @asyncio.coroutine
    def send_message(self, message, image_id=None, otr_status=None, context=None):

        """ChatMessageSegment: parse message"""

        if message is None:
            segments = []
        elif "parser" in context and context["parser"] is False and isinstance(message, str):
            segments = [hangups.ChatMessageSegment(message)]
        elif isinstance(message, str):
            segments = simple_parse_to_segments(message)
            if "passthru" not in context:
                context["passthru"] = {}
            if "originalcontent" not in context["passthru"]:
                context["passthru"]["originalcontent"] = { "message": message,
                                                           "image_id": image_id }
        elif isinstance(message, list):
            segments = message
        else:
            raise TypeError("unknown message type supplied")

        if segments:
            serialised_segments = [seg.serialize() for seg in segments]
        else:
            serialised_segments = None

        """OffTheRecordStatus: determine history"""

        if otr_status is None:
            if "history" not in context:
                context["history"] = True
                try:
                    context["history"] = self.bot.conversations.catalog[self.id_]["history"]

                except KeyError:
                    # rare scenario where a conversation was not refreshed
                    # once the initial message goes through, convmem will be updated
                    logger.warning("could not determine otr for {}".format(conversation_id))

            if context["history"]:
                otr_status = hangups_shim.schemas.OffTheRecordStatus.ON_THE_RECORD
            else:
                otr_status = hangups_shim.schemas.OffTheRecordStatus.OFF_THE_RECORD

        """ExistingMedia: attach previously uploaded media for display"""

        media_attachment = None
        if image_id:
            media_attachment = hangups.hangouts_pb2.ExistingMedia(
                photo = hangups.hangouts_pb2.Photo( photo_id = image_id ))

        """EventAnnotation: combine with client-side storage to allow custom messaging context"""

        annotations = []
        if "reprocessor" in context:
            annotations.append( hangups.hangouts_pb2.EventAnnotation(
                type = 1025,
                value = context["reprocessor"]["id"] ))

        # define explicit "passthru" in context to "send" any type of variable
        if "passthru" in context:
            annotations.append( hangups.hangouts_pb2.EventAnnotation(
                type = 1026,
                value = self.bot._handlers.register_passthru(context["passthru"]) ))

        # always implicitly "send" the entire context dictionary
        annotations.append( hangups.hangouts_pb2.EventAnnotation(
            type = 1027,
            value = self.bot._handlers.register_context(context) ))

        """send the message"""

        with (yield from asyncio.Lock()):
            yield from self._client.send_chat_message(
                hangups.hangouts_pb2.SendChatMessageRequest(
                    request_header = self._client.get_request_header(),
                    message_content = hangups.hangouts_pb2.MessageContent( segment=serialised_segments ),
                    existing_media = media_attachment,
                    annotation = annotations,
                    event_request_header = hangups.hangouts_pb2.EventRequestHeader(
                        conversation_id=hangups.hangouts_pb2.ConversationId( id=self.id_ ),
                        client_generated_id=self._client.get_client_generated_id(),
                        expected_otr = otr_status )))
