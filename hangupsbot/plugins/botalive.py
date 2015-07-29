import asyncio, datetime, logging, time

import hangups

import plugins

import threadmanager


logger = logging.getLogger(__name__)


def _initialise(bot):
    loop = asyncio.get_event_loop()
    threadmanager.start_thread(_periodic_watermark_update, args=(
        bot,
        loop))


def _periodic_watermark_update(bot, loop):
    """runs in a separate thread - to prevent the processor from being
    consumed entirely, we sleep for 5 seconds on each loop iteration"""

    asyncio.set_event_loop(loop)

    last_run = [0, 0]

    watermarkUpdater = watermark_updater(bot)

    while True:
        timestamp = time.time()

        time.sleep(5)

        botalive = bot.get_config_option("botalive")
        if not botalive:
            continue

        """every 15 minutes: update watermark of global admin 1-on-1s"""
        if "admins" in botalive and timestamp - last_run[0] > 900:
            admins = bot.get_config_option('admins')
            for admin in admins:
                if bot.memory.exists(["user_data", admin, "1on1"]):
                    conv_id = bot.memory.get_by_path(["user_data", admin, "1on1"])
                    watermarkUpdater.add(conv_id)
            watermarkUpdater.start()
            last_run[0] = timestamp

        """every 3 hours: update watermark of all groups"""
        if "groups" in botalive and timestamp - last_run[1] > 10800:
            for conv_id, conv_data in bot.conversations.get().items():
                if conv_data["type"] == "GROUP":
                    watermarkUpdater.add(conv_id)
            watermarkUpdater.start()
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

    def start(self):
        if self.busy:
            return

        self.busy = True

        self.update_next_conversation()

    def update_next_conversation(self):
        if len(self.queue) > 0:
            conv_id = self.queue.pop(0)
        else:
            self.busy = False
            self._current_convid = False
            self._critical_errors = 0
            return

        logger.info("watermarking {}".format(conv_id))

        self._current_convid = conv_id
        asyncio.async(
            self.bot._client.updatewatermark(
                self._current_convid,
                datetime.datetime.fromtimestamp(time.time()))
        ).add_done_callback(self.after_update)


    def after_update(self, future):
        """Handle showing an error if a message fails to send"""
        try:
            future.result()
            if self._critical_errors > 0:
                self._critical_errors = self._critical_errors - 1

        except Exception as e:
            self._critical_errors = self._critical_errors + 1

            if self._critical_errors > max(10, len(self.queue) * 2):
                logger.error("critical error threshold reached, exiting thread")
                exit()

            self.add(self._current_convid)
            time.sleep(1)

        self.update_next_conversation()
