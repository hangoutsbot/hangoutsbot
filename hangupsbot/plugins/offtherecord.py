"""Allows the user to configure the bot to watch for the Off the Record status changing
and change it back to a default status accordingly"""

import asyncio, logging

import hangups

import plugins

from commands import command


logger = logging.getLogger(__name__)


otr_options = [
    "DONT_CARE",    # No need to monitor the history setting for this hangout
    "OFF",          # OFF_THE_RECORD_STATUS_OFF_THE_RECORD
    "ON"            # OFF_THE_RECORD_STATUS_ON_THE_RECORD"
]

def _initialise(bot):
    plugins.register_handler(_watch_otr, type="history")
    plugins.register_admin_command(["offtherecord"])


@asyncio.coroutine
def _watch_otr(bot, event, command):

    memory_otr_path = ["conversations", event.conv_id, "otr"]

    memory_otr_status = False
    if bot.memory.exists(memory_otr_path):
        memory_otr_status = bot.memory.get_by_path(memory_otr_path)

    if memory_otr_status:
        # seems to be a valid otr_status for the current conversation

        authorised_otr_change = False

        if not authorised_otr_change:
            # admins can always change the status
            admins_list = bot.get_config_suboption(event.conv_id, "admins")
            if event.user_id.chat_id in admins_list:
                authorised_otr_change = True

        if authorised_otr_change:
            bot.memory.set_by_path(memory_otr_path, event.conv_event.new_otr_status)
            bot.memory.save()
            memory_otr_status = event.conv_event.otr_status

        if event.conv_event.new_otr_status != memory_otr_status:
            hangups_user = bot.get_hangups_user(event.user_id.chat_id)
            logger.warning(
                "Unauthorised OTR change by {} ({}) in {}. Resetting to: {}"
                    .format( hangups_user.full_name,
                             event.user_id.chat_id,
                             event.conv_id,
                             memory_otr_status ))

            yield from otr_toggle(bot, event.conv_id, memory_otr_status)

            message = "<i>I'm sorry {}, I'm afraid I can't do that.</i>".format(event.user.first_name)
            yield from bot.coro_send_message(event.conv_id, message, context={"history": False})


def offtherecord(bot, event, *args):
    """<br/>/bot <i><b>offtherecord</b></i><br/>Defines whether the bot will control the history in the hangout.<br /><u>Usage</u><br />/bot <i><b>offtherecord</b></i>"""

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

    if bot.memory.exists(["conversations", event.conv_id, "otr"]):
        new_otr = (bot.memory.get_by_path(["conversations", event.conv_id, "otr"]) + 1)%3
    else:
        # No path was found. Is this your first setup?
        new_otr = 1 # Use 1 or you get stuck in a loop of 0

    if otr_options[new_otr] is not "DONT_CARE":
        # Update the otr setting
        for conv in conv_id_list:
            bot.memory.set_by_path(["conversations", conv, "otr"], new_otr)
            yield from otr_toggle(bot, conv, new_otr)
    else:
        # If setting is DONT_CARE (i.e. the bot shouldn"t control it any more) then clear the conversation memory entry
        for conv in conv_id_list:
            conv_settings = bot.memory.get_by_path(["conversations", conv])
            del conv_settings["otr"] # remove setting
            bot.memory.set_by_path(["conversations", conv], conv_settings)


    bot.memory.save()

    # Echo the current otr setting
    if otr_options[new_otr] is not "DONT_CARE":
        message = "<i><b>History {0}</b> will be maintained in this hangout.</i>".format(otr_options[new_otr])
    else:
        message = "<i>The history setting will no longer be maintained in this hangout.</i>".format(otr_options[new_otr])

    logger.debug("{0} ({1}) has toggled the OTR status in {2} to {3}".format(event.user.full_name, event.user.id_.chat_id, event.conv_id, otr_options[new_otr]))

    yield from bot.coro_send_message(conv, message, context={"history": False})


@asyncio.coroutine
def otr_toggle(bot, conv, new_otr):

    yield from bot.modify_otr_status(conv, int(new_otr))

