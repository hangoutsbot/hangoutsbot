import asyncio, datetime, logging, time

import hangups

import plugins

import threadmanager

logger = logging.getLogger(__name__)


internal = {}


def _initialise(bot):
    config_botalive = bot.get_config_option("botalive") or {}
    if not config_botalive:
        return

    _new_config = {}
    if isinstance(config_botalive, list):
        if "admins" in config_botalive:
            _new_config["admins"] = 900
        if "groups" in config_botalive:
            _new_config["groups"] = 10800
        config_botalive = _new_config

    if "admin" in config_botalive and config_botalive["admin"] < 60:
        config_botalive["admin"] = 60
    if "groups" in config_botalive and config_botalive["groups"] < 60:
        config_botalive["groups"] = 60

    logger.info("timing {}".format(config_botalive))

    plugins.start_asyncio_task(_periodic_watermark_update, config_botalive)


@asyncio.coroutine
def _periodic_watermark_update(bot, config_botalive):
    """runs in a separate thread - to prevent the processor from being
    consumed entirely, we sleep for 5 seconds on each loop iteration"""

    last_run = [0, 0]

    watermarkUpdater = watermark_updater(bot)

    while True:
        timestamp = time.time()

        yield from asyncio.sleep(5)

        """every 15 minutes: update watermark of global admin 1-on-1s"""
        if "admins" in config_botalive and timestamp - last_run[0] > config_botalive["admins"]:
            admins = bot.get_config_option('admins')
            for admin in admins:
                if bot.memory.exists(["user_data", admin, "1on1"]):
                    conv_id = bot.memory.get_by_path(["user_data", admin, "1on1"])
                    watermarkUpdater.add(conv_id)
            yield from watermarkUpdater.start()
            last_run[0] = timestamp

        """every 3 hours: update watermark of all groups"""
        if "groups" in config_botalive and timestamp - last_run[1] > config_botalive["groups"]:
            for conv_id, conv_data in bot.conversations.get().items():
                if conv_data["type"] == "GROUP":
                    watermarkUpdater.add(conv_id)
            yield from watermarkUpdater.start()
            last_run[1] = timestamp


class watermark_updater:
    """implement a simple queue to update the watermarks sequentially instead of all-at-once

    usage: .add("<conv id>") as many conversation ids as you want, then call .start()

    if a hangups exception is raised, log the exception and output to console
    """

    bot = None

    queue = []
    busy = False

    _current_convid = False
    _critical_errors = 0 # track repeated errors during asyncio.async call, resets when batch finished

    def __init__(self, bot):
        self.bot = bot

    def add(self, conv_id):
        if conv_id not in self.queue:
            self.queue.append(conv_id)


    @asyncio.coroutine
    def start(self):
        if self.busy:
            return

        self.busy = True

        yield from self.update_next_conversation()


    @asyncio.coroutine
    def update_next_conversation(self):
        if len(self.queue) > 0:
            conv_id = self.queue.pop(0)

        else:
            self.busy = False
            self._current_convid = False
            self._critical_errors = 0

            logger.debug("no more conversations to watermark")
            return

        logger.info("watermarking {}".format(conv_id))

        self._current_convid = conv_id

        try:
            yield from self.bot._client.updatewatermark( self._current_convid, 
                                                         datetime.datetime.fromtimestamp(time.time()))

            if self._critical_errors > 0:
                self._critical_errors = self._critical_errors - 1

        except Exception as e:
            self._critical_errors = self._critical_errors + 1

            if self._critical_errors > max(10, len(self.queue) * 2):
                logger.error("critical error threshold reached, clearing queue")
                self.queue = []

            else:
                logger.exception("WATERMARK FAILED FOR {}".format(self._current_convid))
                self.add(self._current_convid)

                yield from asyncio.sleep(1)

        yield from self.update_next_conversation()
