"""Allows the user to configure the bot to watch for the Link Sharing  status changing
and change it back to a default status accordingly"""

import asyncio, logging

import hangups

import plugins

from commands import command


logger = logging.getLogger(__name__)


gls_options = [
    "DONT_CARE",    # No need to monitor the link join setting for this hangout
    "ON",           # GROUP_LINK_SHARING_STATUS_ON
    "OFF"           # GROUP_LINK_SHARING_STATUS_OFF
]

def _initialise(bot):
    plugins.register_handler(_watch_gls, type="linkshare")
    plugins.register_admin_command(["linksharing"])


@asyncio.coroutine
def _watch_gls(bot, event, command):

    memory_gls_path = ["conversations", event.conv_id, "gls"]

    memory_gls_status = False
    if bot.memory.exists(memory_gls_path):
        memory_gls_status = bot.memory.get_by_path(memory_gls_path)

    if memory_gls_status:
        # seems to be a valid gls_status for the current conversation

        authorised_gls_change = False

        if not authorised_gls_change:
            # admins can always change the status
            admins_list = bot.get_config_suboption(event.conv_id, "admins")
            if event.user_id.chat_id in admins_list:
                authorised_gls_change = True

        if authorised_gls_change:
            bot.memory.set_by_path(memory_gls_path, event.conv_event.new_status)
            bot.memory.save()
            memory_gls_status = event.conv_event.new_status

        if event.conv_event.new_status != memory_gls_status:
            hangups_user = bot.get_hangups_user(event.user_id.chat_id)
            logger.warning(
                "Unauthorised GLS change by {} ({}) in {}. Resetting to: {}"
                    .format( hangups_user.full_name,
                             event.user_id.chat_id,
                             event.conv_id,
                             memory_gls_status ))

            yield from gls_toggle(bot, event.conv_id, memory_gls_status)

            message = "<i>I'm sorry {}, I'm afraid I can't do that.</i>".format(event.user.first_name)
            yield from bot.coro_send_message(event.conv_id, message, context={"history": False})


def linksharing(bot, event, *args):
    """<br/>/bot <i><b>linksharing</b></i><br/>Defines whether the bot will control the link sharing status in the hangout.<br /><u>Usage</u><br />/bot <i><b>linksharing</b></i>"""

    conv_id_list = [event.conv_id]

    # Check to see if sync is active
    syncouts = bot.get_config_option('sync_rooms')

    # If yes, then find out if the current room is part of one.
    # If it is, then add the rest of the rooms to the list of conversations to process
    if syncouts:
        for sync_room_list in syncouts:
            if event.conv_id in sync_room_list:
                for conv in sync_room_list:
                    if not conv in conv_id_list:
                        conv_id_list.append(conv)


    # If no memory entry exists for the conversation, create it.
    if not bot.memory.exists(["conversations"]):
        bot.memory.set_by_path(["conversations"],{})

    for conv in conv_id_list:
        if not bot.memory.exists(["conversations",conv]):
            bot.memory.set_by_path(["conversations",conv],{})

    if bot.memory.exists(["conversations", event.conv_id, "gls"]):
        new_gls = (bot.memory.get_by_path(["conversations", event.conv_id, "gls"]) + 1)%3
    else:
        # No path was found. Is this your first setup?
        new_gls = 1 # Use 1 or you get stuck in a loop of 0

    if gls_options[new_gls] is not "DONT_CARE":
        # Update the gls setting
        for conv in conv_id_list:
            bot.memory.set_by_path(["conversations", conv, "gls"], new_gls)
            yield from gls_toggle(bot, conv, new_gls)
    else:
        # If setting is DONT_CARE (i.e. the bot shouldn"t control it any more) then clear the conversation memory entry
        for conv in conv_id_list:
            conv_settings = bot.memory.get_by_path(["conversations", conv])
            del conv_settings["gls"] # remove setting
            bot.memory.set_by_path(["conversations", conv], conv_settings)


    bot.memory.save()

    # Echo the current gls setting
    if gls_options[new_gls] is not "DONT_CARE":
        message = "<i><b>Link sharing {0}</b> will be maintained in this hangout.</i>".format(gls_options[new_gls])
    else:
        message = "<i>The link sharing setting will no longer be maintained in this hangout.</i>".format(gls_options[new_gls])

    logger.debug("{0} ({1}) has toggled the gls status in {2} to {3}".format(event.user.full_name, event.user.id_.chat_id, event.conv_id, gls_options[new_gls]))

    yield from bot.coro_send_message(conv, message, context={"history": False})


@asyncio.coroutine
def gls_toggle(bot, conv, new_gls):

    yield from bot.set_group_link_sharing_enabled(conv, int(new_gls))
