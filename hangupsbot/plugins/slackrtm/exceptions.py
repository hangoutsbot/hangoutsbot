class ParseError(Exception):
    pass


class AlreadySyncingError(Exception):
    pass


class NotSyncingError(Exception):
    pass


class ConnectionFailedError(Exception):
    pass


class IncompleteLoginError(Exception):
    pass
