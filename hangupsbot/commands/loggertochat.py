import asyncio, logging, logging.handlers, sys

import plugins

logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_admin_command(["lograise", "logconfig"])

    rootLogger = logging.getLogger()
    for handler in rootLogger.handlers:
        if handler.__class__.__name__ == "ChatMessageLogger":
            logger.info("ChatMessageLogger already attached") 
            return

    chatHandler = ChatMessageLogger(bot)

    chatHandler.setFormatter(logging.Formatter("<b>%(levelname)s %(name)s </b>: %(message)s"))
    chatHandler.setLevel(logging.WARNING)
    chatHandler.addFilter(PluginFilter(bot))

    rootLogger.addHandler(chatHandler)


def logconfig(bot, event, loggername, level):
    if loggername in sys.modules:
        config_logging = bot.get_config_option("logging") or {}

        mapping = { "critical": 50,
                    "error": 40,
                    "warning": 30,
                    "info": 20,
                    "debug": 10 }

        effective_level = 0
        if level.isdigit():
            effective_level = int(level)
            if effective_level < 0:
                effective_level = 0
        elif level.lower() in mapping:
            effective_level = mapping[level]

        if effective_level == 0:
            if loggername in config_logging:
                del config_logging[loggername]
            message = "logging: {} disabled".format(loggername, effective_level)

        else:
            if loggername in config_logging:
                current = config_logging[loggername]
            else:
                current = { "level": 0 }

            current["level"] = effective_level

            config_logging[loggername] = current
            message = "logging: {} set to {} / {}".format(loggername, effective_level, level)

        bot.config.set_by_path(["logging"], config_logging)
        bot.config.save()

    else:
        message = "logging: {} not found".format(loggername)

    yield from bot.coro_send_message(event.conv_id, message)


def lograise(bot, event, *args):
    level = (''.join(args) or "DEBUG").upper()

    if level == "CRITICAL":
        logger.critical("This is a CRITICAL log message")
    elif level == "ERROR":
        logger.error("This is an ERROR log message")
    elif level == "WARNING":
        logger.warning("This is a WARNING log message")
    elif level == "INFO":
        logger.info("This is an INFO log message")
    elif level == "DEBUG":
        logger.debug("This is a DEBUG log message")


class PluginFilter(logging.Filter):
    def __init__(self, bot):
        self.bot = bot
        logging.Filter.__init__(self)

    def filter(self, record):
        logging = self.bot.get_config_option("logging") or {}
        if not logging:
            return False

        if record.name not in logging:
            return False

        if record.levelno < logging[record.name]["level"]:
            return False

        return True


class ChatMessageLogger(logging.Handler):
    def __init__(self, bot):
        self.bot = bot
        logging.Handler.__init__(self)

    def emit(self, record):
        message = self.format(record)
        convs = self.bot.conversations.get("tag:receive-logs")
        for conv_id in convs.keys():
            asyncio.async(
                self.bot.coro_send_message(conv_id, message)
            ).add_done_callback(lambda future: future.result())
