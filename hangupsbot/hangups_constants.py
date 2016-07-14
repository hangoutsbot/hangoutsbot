"""1 to 1 mappings of hangups legacy enums, but as standard classes"""
import hangups


class TypingStatus:

    """Typing statuses."""

    TYPING = hangups.schemas.TypingStatus.TYPING
    PAUSED = hangups.schemas.TypingStatus.PAUSED
    STOPPED = hangups.schemas.TypingStatus.STOPPED


class FocusStatus:

    """Focus statuses."""

    FOCUSED = hangups.schemas.FocusStatus.FOCUSED
    UNFOCUSED = hangups.schemas.FocusStatus.UNFOCUSED


class FocusDevice:

    """Focus devices."""

    DESKTOP = hangups.schemas.FocusDevice.DESKTOP
    MOBILE = hangups.schemas.FocusDevice.MOBILE
    UNSPECIFIED = None


class ConversationType:

    """Conversation type."""

    STICKY_ONE_TO_ONE = hangups.schemas.ConversationType.STICKY_ONE_TO_ONE
    GROUP = hangups.schemas.ConversationType.GROUP


class ClientConversationView:

    """Conversation view."""

    UNKNOWN_CONVERSATION_VIEW = hangups.schemas.ClientConversationView.UNKNOWN_CONVERSATION_VIEW
    INBOX_VIEW = hangups.schemas.ClientConversationView.INBOX_VIEW
    ARCHIVED_VIEW = hangups.schemas.ClientConversationView.ARCHIVED_VIEW


class ClientNotificationLevel:

    """Notification level."""

    UNKNOWN = None
    QUIET = hangups.schemas.ClientNotificationLevel.QUIET
    RING = hangups.schemas.ClientNotificationLevel.RING


class ClientConversationStatus:

    """Conversation status."""

    UNKNOWN_CONVERSATION_STATUS = hangups.schemas.ClientConversationStatus.UNKNOWN_CONVERSATION_STATUS
    INVITED = hangups.schemas.ClientConversationStatus.INVITED
    ACTIVE = hangups.schemas.ClientConversationStatus.ACTIVE
    LEFT = hangups.schemas.ClientConversationStatus.LEFT


class SegmentType:

    """Message content segment type."""

    TEXT = hangups.schemas.SegmentType.TEXT
    LINE_BREAK = hangups.schemas.SegmentType.LINE_BREAK
    LINK = hangups.schemas.SegmentType.LINK


class MembershipChangeType:

    """Conversation membership change type."""

    JOIN = hangups.schemas.MembershipChangeType.JOIN
    LEAVE = hangups.schemas.MembershipChangeType.LEAVE


class ClientHangoutEventType:

    """Hangout event type."""

    START_HANGOUT = hangups.schemas.ClientHangoutEventType.START_HANGOUT
    END_HANGOUT = hangups.schemas.ClientHangoutEventType.END_HANGOUT
    JOIN_HANGOUT = hangups.schemas.ClientHangoutEventType.JOIN_HANGOUT
    LEAVE_HANGOUT = hangups.schemas.ClientHangoutEventType.LEAVE_HANGOUT
    HANGOUT_COMING_SOON = hangups.schemas.ClientHangoutEventType.HANGOUT_COMING_SOON
    ONGOING_HANGOUT = hangups.schemas.ClientHangoutEventType.ONGOING_HANGOUT


class OffTheRecordStatus:

    """Off-the-record status."""

    OFF_THE_RECORD = hangups.schemas.OffTheRecordStatus.OFF_THE_RECORD
    ON_THE_RECORD = hangups.schemas.OffTheRecordStatus.ON_THE_RECORD


class ClientOffTheRecordToggle:

    """Off-the-record toggle status."""

    ENABLED = hangups.schemas.ClientOffTheRecordToggle.ENABLED
    DISABLED = hangups.schemas.ClientOffTheRecordToggle.DISABLED


class ActiveClientState:

    """Active client state."""

    NO_ACTIVE_CLIENT = hangups.schemas.ActiveClientState.NO_ACTIVE_CLIENT
    IS_ACTIVE_CLIENT = hangups.schemas.ActiveClientState.IS_ACTIVE_CLIENT
    OTHER_CLIENT_IS_ACTIVE = hangups.schemas.ActiveClientState.OTHER_CLIENT_IS_ACTIVE
