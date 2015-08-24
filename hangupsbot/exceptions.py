class SuppressHandler(Exception):
    pass

class SuppressAllHandlers(Exception):
    pass

class SuppressEventHandling(Exception):
    pass


class HangupsBotExceptions:
    def __init__(self):
        self.SuppressHandler = SuppressHandler
        self.SuppressAllHandlers = SuppressAllHandlers
        self.SuppressEventHandling = SuppressEventHandling

