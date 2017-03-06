from hangups import hangouts_pb2

from hangups import ( ChatMessageEvent,
                      MembershipChangeEvent,
                      RenameEvent )

from hangups.conversation_event import ConversationEvent as conversation_event

from hangups.conversation_event import ChatMessageSegment

from hangups.exceptions import NetworkError

from collections import Mapping, namedtuple

def namedtuplify(mapping, name='NT'):  # thank you https://gist.github.com/hangtwenty/5960435
    """ Convert mappings to namedtuples recursively. """
    if isinstance(mapping, Mapping):
        for key, value in list(mapping.items()):
            mapping[key] = namedtuplify(value)
        return namedtuple_wrapper(name, **mapping)
    elif isinstance(mapping, list):
        return [namedtuplify(item) for item in mapping]
    return mapping

def namedtuple_wrapper(name, **kwargs):
    wrap = namedtuple(name, kwargs)
    return wrap(**kwargs)


LegacySchema = {
    'ClientHangoutEventType': {
        'END_HANGOUT': hangouts_pb2.HANGOUT_EVENT_TYPE_END },
    'OffTheRecordStatus': {
        'ON_THE_RECORD': hangouts_pb2.OFF_THE_RECORD_STATUS_ON_THE_RECORD,
        'OFF_THE_RECORD': hangouts_pb2.OFF_THE_RECORD_STATUS_OFF_THE_RECORD,
        'UNKNOWN': hangouts_pb2.OFF_THE_RECORD_STATUS_UNKNOWN },
    'TypingStatus': {
        'TYPING': hangouts_pb2.TYPING_TYPE_STARTED,
        'PAUSED': hangouts_pb2.TYPING_TYPE_PAUSED,
        'STOPPED': hangouts_pb2.TYPING_TYPE_STOPPED,
        'UNKNOWN': hangouts_pb2.TYPING_TYPE_UNKNOWN },
    'ConversationType': {
        'STICKY_ONE_TO_ONE': hangouts_pb2.CONVERSATION_TYPE_ONE_TO_ONE,
        'GROUP': hangouts_pb2.CONVERSATION_TYPE_GROUP,
        'UNKNOWN': hangouts_pb2.CONVERSATION_TYPE_UNKNOWN },
    'SegmentType': {
        'TEXT': hangouts_pb2.SEGMENT_TYPE_TEXT,
        'LINE_BREAK': hangouts_pb2.SEGMENT_TYPE_LINE_BREAK,
        'LINK': hangouts_pb2.SEGMENT_TYPE_LINK },
    'MembershipChangeType' : {
        'JOIN': hangouts_pb2.MEMBERSHIP_CHANGE_TYPE_JOIN,
        'LEAVE': hangouts_pb2.MEMBERSHIP_CHANGE_TYPE_LEAVE },
    'ClientNotificationLevel' : {
        'UNKNOWN': hangouts_pb2.NOTIFICATION_LEVEL_UNKNOWN,
        'QUIET': hangouts_pb2.NOTIFICATION_LEVEL_QUIET,
        'RING': hangouts_pb2.NOTIFICATION_LEVEL_RING },
    'ClientConversationStatus' : {
        'UNKNOWN': hangouts_pb2.CONVERSATION_STATUS_UNKNOWN,
        'INVITED': hangouts_pb2.CONVERSATION_STATUS_INVITED,
        'ACTIVE': hangouts_pb2.CONVERSATION_STATUS_ACTIVE,
        'LEFT': hangouts_pb2.CONVERSATION_STATUS_LEFT },
    'ClientConversationView' : {
        'UNKNOWN': hangouts_pb2.CONVERSATION_VIEW_UNKNOWN,
        'INBOX_VIEW': hangouts_pb2.CONVERSATION_VIEW_INBOX,
        'ARCHIVED_VIEW': hangouts_pb2.CONVERSATION_VIEW_ARCHIVED }}

schemas = namedtuplify(LegacySchema)

SegmentType = schemas.SegmentType
MembershipChangeType = schemas.MembershipChangeType
