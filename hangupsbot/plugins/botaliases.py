"""aliases for the bot"""
import logging

import plugins


logger = logging.getLogger(__name__)


def _initialise(bot):
    """load in bot aliases from memory, create defaults if none"""

    if bot.memory.exists(["bot.command_aliases"]):
        bot_command_aliases = bot.memory.get("bot.command_aliases")
    else:
        myself = bot.user_self()
        # basic
        bot_command_aliases = ["/bot"]
        # /<first name fragment>
        first_fragment = myself["full_name"].split()[0].lower()
        if first_fragment and first_fragment != "unknown":
            alias_firstname = "/" + first_fragment
            bot_command_aliases.append(alias_firstname)
        # /<chat_id>
        bot_command_aliases.append("/" + myself["chat_id"])

        bot.memory.set_by_path(["bot.command_aliases"], bot_command_aliases)
        bot.memory.save()

    if not isinstance(bot_command_aliases, list):
        bot_command_aliases = []

    if len(bot_command_aliases) == 0:
        bot.append("/bot")

    bot._handlers.bot_command = bot_command_aliases
    logger.info("aliases: {}".format(bot_command_aliases))

    plugins.register_user_command(["botalias"])

    return []


def botalias(bot, event, *args):
    """shows, adds and removes bot command aliases"""

    if len(args) == 0:
        yield from bot.coro_send_message(
            event.conv,
            _("<i>bot alias: {}</i>").format(
                ", ".join(bot._handlers.bot_command)))
    else:
        admins_list = bot.get_config_suboption(event.conv_id, 'admins')
        if event.user_id.chat_id in admins_list:
            _aliases = list(bot._handlers.bot_command)
            if len(args) == 1:
                """add alias"""
                if args[0].lower() not in _aliases:
                    _aliases.append(args[0].lower())
            else:
                """remove aliases, supply list to remove more than one"""
                if args[0].lower() == "remove":
                    for _alias in args[1:]:
                        _aliases.remove(_alias.lower())

            if _aliases != bot._handlers.bot_command:
                if len(_aliases) == 0:
                    _aliases = ["/bot"]

                bot.memory.set_by_path(["bot.command_aliases"], _aliases)
                bot.memory.save()

                bot._handlers.bot_command = _aliases

            botalias(bot, event) # run with no arguments
        else:
            yield from bot.coro_send_message(
                event.conv,
                _("<i>not authorised to change bot alias</i>"))
