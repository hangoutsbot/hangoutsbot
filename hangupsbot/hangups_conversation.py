import asyncio, logging, time

from collections import namedtuple

import hangups


logger = logging.getLogger(__name__)


ConversationID = namedtuple('conversation_id', ['id_'])

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
            otr_status = hangups.schemas.OffTheRecordStatus.ON_THE_RECORD
        else:
            otr_status = hangups.schemas.OffTheRecordStatus.OFF_THE_RECORD

        if permamem_conv["type"] == "GROUP":
            type_ = hangups.schemas.ConversationType.GROUP
        else:
            type_ = hangups.schemas.ConversationType.STICKY_ONE_TO_ONE

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

        conversation_id = ConversationID(id_=conv_id)

        self_conversation_state = SelfConversationState( active_timestamp=timestamp_now,
                                                         invite_timestamp=timestamp_now,
                                                         inviter_id=hangups.user.UserID( chat_id=bot_user["chat_id"],
                                                                                         gaia_id=bot_user["chat_id"] ),
                                                         notification_level=hangups.schemas.ClientNotificationLevel.RING,
                                                         self_read_state=LatestRead( latest_read_timestamp=latest_read_timestamp,
                                                                                     participant_id=hangups.user.UserID( chat_id=bot_user["chat_id"],
                                                                                                                         gaia_id=bot_user["chat_id"] )),
                                                         sort_timestamp=sort_timestamp,
                                                         status=hangups.schemas.ClientConversationStatus.ACTIVE,
                                                         view=hangups.schemas.ClientConversationView.INBOX_VIEW )

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
    def __init__(self, _client, id_):
        self._client = _client
        self.id_ = id_

    @asyncio.coroutine
    def send_message(self, segments, image_id=None, otr_status=None):
        with (yield from asyncio.Lock()):
            if segments:
                serialised_segments = [seg.serialize() for seg in segments]
            else:
                serialised_segments = None

            yield from self._client.sendchatmessage(
                self.id_, serialised_segments,
                image_id=image_id, otr_status=otr_status
            )
