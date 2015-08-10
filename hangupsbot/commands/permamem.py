import logging

import plugins


logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_admin_command(["dumpconv", "dumpunknownusers", "resetunknownusers", "refreshusermemory", "removeconvrecord", "makeallusersindefinite"])


def dumpconv(bot, event, *args):
    """dump all conversations known to the bot"""
    text_search = " ".join(args)
    lines = []
    all_conversations = bot.conversations.get().items()
    for convid, convdata in all_conversations:
        if text_search.lower() in convdata["title"].lower():
            lines.append("`{}` <em>{}</em> {}<br />... `{}` history: {} <br />... <b>{}</b>".format(
                convid, convdata["source"], len(convdata["participants"]), convdata["type"], convdata["history"], convdata["title"]))
    lines.append("<b><em>Totals: {}/{}</em></b>".format(len(lines), len(all_conversations)))
    yield from bot.coro_send_message(event.conv, "<br />".join(lines))


def dumpunknownusers(bot, event, *args):
    """lists cached users records with full name, first name as unknown, and is_definitive"""
    logger.info("dumpunknownusers started")

    if bot.memory.exists(["user_data"]):
        for chat_id in bot.memory["user_data"]:
            if "_hangups" in bot.memory["user_data"][chat_id]:
                _hangups = bot.memory["user_data"][chat_id]["_hangups"]
                if _hangups["is_definitive"]:
                    if _hangups["full_name"].upper() == "UNKNOWN" and _hangups["full_name"] == _hangups["first_name"]:
                        logger.info("dumpunknownusers {}".format(_hangups))

    logger.info("dumpunknownusers finished")

    yield from bot.coro_send_message(event.conv, "<b>please see log/console</b>")


def resetunknownusers(bot, event, *args):
    """resets cached users records with full name, first name as unknown, and is_definitive"""
    logger.info("resetunknownusers started")

    if bot.memory.exists(["user_data"]):
        for chat_id in bot.memory["user_data"]:
            if "_hangups" in bot.memory["user_data"][chat_id]:
                _hangups = bot.memory["user_data"][chat_id]["_hangups"]
                if _hangups["is_definitive"]:
                    if _hangups["full_name"].upper() == "UNKNOWN" and _hangups["full_name"] == _hangups["first_name"]:
                        logger.info("resetunknownusers {}".format(_hangups))
                        bot.memory.set_by_path(["user_data", chat_id, "_hangups", "is_definitive"], False)
    bot.memory.save()

    logger.info("resetunknownusers finished")

    yield from bot.coro_send_message(event.conv, "<b>please see log/console</b>")


def refreshusermemory(bot, event, *args):
    """refresh specified user chat ids with contact/getentitybyid"""
    logger.info("refreshusermemory started")
    updated = yield from bot.conversations.get_users_from_query(args)
    logger.info("refreshusermemory {} updated".format(updated))
    logger.info("refreshusermemory ended")

    yield from bot.coro_send_message(event.conv, "<b>please see log/console</b>")


def removeconvrecord(bot, event, *args):
    """removes conversation record from memory.json"""
    logger.info("resetunknownusers started")
    if args:
        for conv_id in args:
            bot.conversations.remove(conv_id)
    logger.info("resetunknownusers finished")

    yield from bot.coro_send_message(event.conv, "<b>please see log/console</b>")


def makeallusersindefinite(bot, event, *args):
    """turn off the is_definite flag for all users"""
    logger.info("makeallusersindefinite started")

    if bot.memory.exists(["user_data"]):
        for chat_id in bot.memory["user_data"]:
            if "_hangups" in bot.memory["user_data"][chat_id]:
                _hangups = bot.memory["user_data"][chat_id]["_hangups"]
                if _hangups["is_definitive"]:
                    bot.memory.set_by_path(["user_data", chat_id, "_hangups", "is_definitive"], False)
    bot.memory.save()

    logger.info("makeallusersindefinite finished")

    yield from bot.coro_send_message(event.conv, "<b>please see log/console</b>")
