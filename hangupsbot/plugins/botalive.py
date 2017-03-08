"""plugin to watermark conversations periodically determined by config entry"""

import asyncio
import datetime
import hangups
import logging
import plugins
import random

logger = logging.getLogger(__name__)

def _initialise(bot):
    config_botalive = bot.get_config_option("botalive") or {}
    if not config_botalive:
        return

    if not bot.memory.exists(["conv_data"]):
        # should not come to this, but create it once as we need to store data for each conv in it
        bot.memory.set_by_path(["conv_data"], {})
        bot.memory.save()

    # backwards compatibility
    if isinstance(config_botalive, list):
        _new_config = {}
        if "admins" in config_botalive:
            _new_config["admins"] = 900
        if "groups" in config_botalive:
            _new_config["groups"] = 10800
        bot.config.set_by_path(["botalive"], _new_config)
        bot.config.save()
        config_botalive = _new_config

    if "admins" not in config_botalive and "groups" not in config_botalive:
        return

    watermarkUpdater = watermark_updater(bot)

    if "admins" in config_botalive:
        if config_botalive["admins"] < 60:
            config_botalive["admins"] = 60
        plugins.start_asyncio_task(_periodic_watermark_update, watermarkUpdater, "admins")

    if "groups" in config_botalive:
        if config_botalive["groups"] < 60:
            config_botalive["groups"] = 60
        plugins.start_asyncio_task(_periodic_watermark_update, watermarkUpdater, "groups")

    logger.info("timing {}".format(config_botalive))

    watch_event_types = [
        "message",
        "membership",
        "rename"
        ]
    for event_type in watch_event_types:
        plugins.register_handler(_log_message, event_type)

def _log_message(bot, event, command):
    """log time to conv_data of event conv"""

    conv_id = str(event.conv_id)
    if not bot.memory.exists(["conv_data", conv_id]):
        bot.memory.set_by_path(["conv_data", conv_id], {})
        bot.memory.save()
    bot.memory.set_by_path(["conv_data", conv_id, "botalive"], datetime.datetime.now().timestamp())
    # not worth a dump to disk, skip bot.memory.save()

@asyncio.coroutine
def _periodic_watermark_update(bot, watermarkUpdater, target):
    """
    add conv_ids of 1on1s with bot admins or add group conv_ids to the queue
    to prevent the processor from being consumed entirely, we sleep until the next run or 5 sec
    """

    last_run = datetime.datetime.now().timestamp()

    while True:
        timestamp = datetime.datetime.now().timestamp()
        yield from asyncio.sleep(max(5, last_run - timestamp + bot.config.get_by_path(["botalive", target])))

        if target == "admins":
            bot_admin_ids = bot.get_config_option('admins')
            for admin in bot_admin_ids:
                if bot.memory.exists(["user_data", admin, "1on1"]):
                    conv_id = bot.memory.get_by_path(["user_data", admin, "1on1"])
                    watermarkUpdater.add(conv_id)
        else:
            for conv_id, conv_data in bot.conversations.get().items():
                if conv_data["type"] == "GROUP" and bot.memory.exists(["conv_data", conv_id, "botalive"]):
                    if last_run < bot.memory.get_by_path(["conv_data", conv_id, "botalive"]):
                        watermarkUpdater.add(conv_id)

        last_run = datetime.datetime.now().timestamp()
        yield from watermarkUpdater.start()


class watermark_updater:
    """implement a queue to update the watermarks sequentially instead of all-at-once

    usage:
    .add("<conv id>") as many conversation ids as you want
    .start() will start processing to queue

    if a hangups exception is raised, log the exception and output to console
    to prevent the processor from being consumed entirely and to not act too much as a bot,
     we sleep 5-10sec after each watermark update"""

    def __init__(self, bot):
        self.bot = bot
        self.running = False

        self.queue = set()
        self.failed = dict() # track errors
        self.failed_permanent = set() # track conv_ids that failed 5 times

    def add(self, conv_id):
        if conv_id not in self.failed_permanent:
            self.queue.add(conv_id)

    def start(self):
        if self.running or not len(self.queue):
            return
        self.running = True
        yield from self.update_next_conversation()

    @asyncio.coroutine
    def update_next_conversation(self):
        try:
            conv_id = self.queue.pop()
        except:
            self.running = False
            return

        logger.info("watermarking {}".format(conv_id))

        try:
            yield from self.bot._client.updatewatermark(
                conv_id,
                datetime.datetime.now()
                )
            self.failed.pop(conv_id, None)

        except:
            self.failed[conv_id] = self.failed.get(conv_id, 0) + 1

            if self.failed[conv_id] > 5:
                self.failed_permanent.add(conv_id)
                logger.error("critical error threshold reached for {}".format(conv_id))
            else:
                logger.exception("WATERMARK FAILED FOR {}".format(conv_id))

                # is the bot still in the conv
                if conv_id in self.bot.conversations.get():
                    self.add(conv_id)

        yield from asyncio.sleep(random.randint(5, 10))
        yield from self.update_next_conversation()
