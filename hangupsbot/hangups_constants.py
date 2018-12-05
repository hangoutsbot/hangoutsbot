"""1 to 1 mappings of hangups legacy enums, but as standard classes"""
from hangups import hangouts_pb2


class TypingStatus:

    """Typing statuses."""

    TYPING = hangouts_pb2.TYPING_TYPE_STARTED
    PAUSED = hangouts_pb2.TYPING_TYPE_PAUSED
    STOPPED = hangouts_pb2.TYPING_TYPE_STOPPED

    # new
    UNKNOWN = hangouts_pb2.TYPING_TYPE_UNKNOWN


class FocusStatus:

    """Focus statuses."""

    FOCUSED = hangouts_pb2.FOCUS_TYPE_FOCUSED
    UNFOCUSED = hangouts_pb2.FOCUS_TYPE_UNFOCUSED

    # new
    UNKNOWN = hangouts_pb2.FOCUS_TYPE_UNKNOWN


class FocusDevice:

    """Focus devices."""

    DESKTOP = hangouts_pb2.FOCUS_DEVICE_DESKTOP
    MOBILE = hangouts_pb2.FOCUS_DEVICE_MOBILE
    UNSPECIFIED = hangouts_pb2.FOCUS_DEVICE_UNSPECIFIED


class ConversationType:

    """Conversation type."""

    STICKY_ONE_TO_ONE = hangouts_pb2.CONVERSATION_TYPE_ONE_TO_ONE
    GROUP = hangouts_pb2.CONVERSATION_TYPE_GROUP

    # new
    UNKNOWN_TYPE = hangouts_pb2.CONVERSATION_TYPE_UNKNOWN


class ClientConversationView:

    """Conversation view."""

    UNKNOWN_CONVERSATION_VIEW = hangouts_pb2.CONVERSATION_VIEW_UNKNOWN
    INBOX_VIEW = hangouts_pb2.CONVERSATION_VIEW_INBOX
    ARCHIVED_VIEW = hangouts_pb2.CONVERSATION_VIEW_ARCHIVED


class ClientNotificationLevel:

    """Notification level."""

    UNKNOWN_NOTIFICATION = hangouts_pb2.NOTIFICATION_LEVEL_UNKNOWN
    QUIET = hangouts_pb2.NOTIFICATION_LEVEL_QUIET
    RING = hangouts_pb2.NOTIFICATION_LEVEL_RING


class ClientConversationStatus:

    """Conversation status."""

    UNKNOWN_CONVERSATION_STATUS = hangouts_pb2.CONVERSATION_STATUS_UNKNOWN
    INVITED = hangouts_pb2.CONVERSATION_STATUS_INVITED
    ACTIVE = hangouts_pb2.CONVERSATION_STATUS_ACTIVE
    LEFT = hangouts_pb2.CONVERSATION_STATUS_LEFT


class SegmentType:

    """Message content segment type."""

    TEXT = hangouts_pb2.SEGMENT_TYPE_TEXT
    LINE_BREAK = hangouts_pb2.SEGMENT_TYPE_LINE_BREAK
    LINK = hangouts_pb2.SEGMENT_TYPE_LINK


class MembershipChangeType:

    """Conversation membership change type."""

    JOIN = hangouts_pb2.MEMBERSHIP_CHANGE_TYPE_JOIN
    LEAVE = hangouts_pb2.MEMBERSHIP_CHANGE_TYPE_LEAVE


class ClientHangoutEventType:

    """Hangout event type."""

    START_HANGOUT = hangouts_pb2.HANGOUT_EVENT_TYPE_START
    END_HANGOUT = hangouts_pb2.HANGOUT_EVENT_TYPE_END
    JOIN_HANGOUT = hangouts_pb2.HANGOUT_EVENT_TYPE_JOIN
    LEAVE_HANGOUT = hangouts_pb2.HANGOUT_EVENT_TYPE_LEAVE
    HANGOUT_COMING_SOON = hangouts_pb2.HANGOUT_EVENT_TYPE_COMING_SOON
    ONGOING_HANGOUT = hangouts_pb2.HANGOUT_EVENT_TYPE_ONGOING

    # new
    UNKNOWN_HANGOUT = hangouts_pb2.HANGOUT_EVENT_TYPE_UNKNOWN


class OffTheRecordStatus:

    """Off-the-record status."""

    OFF_THE_RECORD = hangouts_pb2.OFF_THE_RECORD_STATUS_OFF_THE_RECORD
    ON_THE_RECORD = hangouts_pb2.OFF_THE_RECORD_STATUS_ON_THE_RECORD

    UNKNOWN_OFF_THE_RECORD_STATUS = hangouts_pb2.OFF_THE_RECORD_STATUS_UNKNOWN


class ClientOffTheRecordToggle:

    """Off-the-record toggle status."""

    ENABLED = hangouts_pb2.OFF_THE_RECORD_TOGGLE_ENABLED
    DISABLED = hangouts_pb2.OFF_THE_RECORD_TOGGLE_DISABLED

    # new
    UNKNOWN_OFF_THE_RECORD_TOGGLE = hangouts_pb2.OFF_THE_RECORD_TOGGLE_UNKNOWN


class ActiveClientState:

    """Active client state."""

    NO_ACTIVE_CLIENT = hangouts_pb2.ACTIVE_CLIENT_STATE_NO_ACTIVE
    IS_ACTIVE_CLIENT = hangouts_pb2.ACTIVE_CLIENT_STATE_IS_ACTIVE
    OTHER_CLIENT_IS_ACTIVE = hangouts_pb2.ACTIVE_CLIENT_STATE_OTHER_ACTIVE
