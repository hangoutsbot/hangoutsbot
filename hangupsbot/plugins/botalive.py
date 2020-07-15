"""plugin to watermark conversations periodically determined by config entry"""

import asyncio
import datetime
import logging
import plugins
import pprint
import random

import hangups


logger = logging.getLogger(__name__)

_monitored = {}

def _initialise(bot):
    if not bot.get_config_option("botalive"):
        return

    plugins.register_admin_command(["dumpwatermarklogs"])

    plugins.start_asyncio_task(_tick)

    # track events that can modify the watermark
    watch_event_types = [ "message",
                          "membership",
                          "rename" ]
    for event_type in watch_event_types:
        plugins.register_handler(_conv_external_event, event_type)


def dumpwatermarklogs(bot, event, *args):
    """dump the contents of the internal registers to log/console, useful for debugging"""

    yield from bot.coro_send_message(event.conv, "<b>please see log/console</b>")

    pp = pprint.PrettyPrinter(indent=2)
    pp.pprint(_monitored)


def _conv_external_event(bot, event, command):
    """detect non-bot user events indicating activity in a conversation that can advance the watermark"""

    if event.user.is_self:
        return

    conv_id = event.conv_id

    # only track events in conversations that were previously registered by _tick()
    if conv_id in _monitored: # otherwise, this will track events in ALL conversations
        _conv_monitor(bot, conv_id,
            overrides={ 'last_external_event': datetime.datetime.now().timestamp() })


def _conv_monitor(bot, conv_id, overrides={}):
    """monitor conversation states in-memory
    * conversation must already be in permamem
    * supply optional overrides to change defaults/existing state"""

    if conv_id in bot.memory["convmem"]:
        if conv_id not in _monitored:
            # initialise monitoring
            _monitored[conv_id] = { 'errors': [],
                                    'interval_watermark': 3600,
                                    'last_external_event': False,
                                    'last_watermark': False }
        for key, val in overrides.items():
            _monitored[conv_id][key] = val


@asyncio.coroutine
def _tick(bot):
    """manage the list of conversation states and update watermarks sequentially:
    * add/update conversation and watermark intervals dynamically
    * update the watermarks for conversations that need them

    devnote: wrapping loop sleeps for fixed period after everything completes,
        randomness introduced by fuzzing pauses between conversation watermarks"""

    while True:
        config_botalive = bot.get_config_option("botalive") or {}

        watermarked = []
        failed = []
        errors = {}

        # botalive.permafail = <number> of retries before permanently stopping
        #   UNSET/FALSE for default of 5 retries
        if "permafail" not in config_botalive:
            config_botalive['permafail'] = 5

        # botalive.maxfuzz = fuzz watermark update pauses between between 3 and <integer> seconds
        #   UNSET/FALSE to disable fuzzing, pause = fixed 1 second
        if "maxfuzz" not in config_botalive:
            config_botalive['maxfuzz'] = 10
        elif config_botalive["maxfuzz"] is not False and config_botalive["maxfuzz"] < 3:
            config_botalive['maxfuzz'] = 3

        # botalive.admins = minimum amount of <seconds> between watermark updates for admin 1-to-1s
        #   UNSET/FALSE to disable watermarking for admin 1-to-1s
        if "admins" in config_botalive:
            if config_botalive["admins"] < 60:
                config_botalive["admins"] = 60 # minimum: once per minute

            # most efficient way to add admin one-to-ones
            admins = bot.get_config_option('admins')
            for admin in admins:
                if bot.memory.exists(["user_data", admin, "1on1"]):
                    conv_id = bot.memory.get_by_path(["user_data", admin, "1on1"])
                    _conv_monitor(bot, conv_id,
                        overrides={ "interval_watermark": config_botalive["admins"] })

        # botalive.admins = minimum amount of <seconds> between watermark updates for groups
        #   UNSET/FALSE to disable watermarking for groups
        if "groups" in config_botalive:
            if config_botalive["groups"] < 60:
                config_botalive["groups"] = 60 # minimum: once per minute

            # leverage in-built functionality to retrieve group conversations
            for conv_id, conv_data in bot.conversations.get("type:group").items():
                _conv_monitor(bot, conv_id,
                    overrides={ "interval_watermark": config_botalive["groups"] })

        for conv_id, conv_state in _monitored.items():
            now = datetime.datetime.now().timestamp()

            """devnote: separation of verbose logic for clarity - watermark IF:
            * conversation not watermarked before (after bot restart), OR
            * non-bot event moves the bot watermark behind, and configured interval has passed"""
            do_watermark = ( conv_state['last_watermark'] is False
                             or ( conv_state["last_external_event"] is not False
                                  and conv_state["last_external_event"] > conv_state['last_watermark']
                                  and conv_state['last_watermark'] + conv_state['interval_watermark'] < now ))

            if do_watermark and len(conv_state['errors']) < config_botalive['permafail']:
                try:
                    _timestamp = yield from _conv_watermark_now(bot, conv_id)
                    _conv_monitor(bot, conv_id,
                        overrides={ "errors": [], "last_watermark": _timestamp })
                    watermarked.append(conv_id)

                except Exception as e:
                    text_exception = str(e)
                    conv_state["errors"].append(text_exception)
                    _conv_monitor(bot, conv_id,
                        overrides={ "errors": conv_state["errors"] })
                    failed.append(conv_id)
                    if text_exception in errors:
                        errors[text_exception].append(conv_id)
                    else:
                        errors[text_exception] =  [conv_id]

                if config_botalive['maxfuzz']:
                    pause = random.randint(3, config_botalive['maxfuzz'])
                else:
                    pause = 1
                yield from asyncio.sleep(pause)

        if watermarked or failed or errors:
            logger.info("success: {}, failed: {}, unique errors: {}".format( len(watermarked),
                                                                             len(failed),
                                                                             list(errors.keys()) ))

        yield from asyncio.sleep(60)


@asyncio.coroutine
def _conv_watermark_now(bot, conv_id):
    """watermarks the supplied conversation by its id, returns float timestamp
    devnote: this is a direct-to-hangups call, and should remain separate for migration between library versions"""

    now = datetime.datetime.now()
    yield from bot._client.update_watermark(
        hangups.hangouts_pb2.UpdateWatermarkRequest(
            request_header = bot._client.get_request_header(),
            conversation_id = hangups.hangouts_pb2.ConversationId(
                id = conv_id ),
            last_read_timestamp = int(now.strftime("%s")) * 1000000 ))
    return now.timestamp()
