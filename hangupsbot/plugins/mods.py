"""
Plugin for monitoring new adds to HOs and alerting if users were not added by an admin or mod.
Add mods to the config.json file either globally or on an individual HO basis.
Add a "watch_new_adds": true  parameter to individual HOs in the config.json file. 
"""

import asyncio
import hangups


def _initialise(Handlers, bot=None):
    Handlers.register_handler(_watch_new_adds, type="membership")
    return []


@asyncio.coroutine
def _watch_new_adds(bot, event, command):
    # Check if watching for new adds is enabled
    if not bot.get_config_suboption(event.conv_id, 'watch_new_adds'):
        return
    # Generate list of added or removed users
    event_users = [event.conv.get_user(user_id) for user_id
                   in event.conv_event.participant_ids]
    names = ', '.join([user.full_name for user in event_users])

    # JOIN
    if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        # Check if the user who added people is a mod or admin
        mods_list = bot.get_config_suboption(event.conv_id, 'mods')
        admins_list = bot.get_config_suboption(event.conv_id, 'admins')
        if event.user_id.chat_id in admins_list or event.user_id.chat_id in mods_list:
            return
        else:
            bot.send_message_parsed(event.conv, '<b>!!! Warning !!!</b>')
            bot.send_message_parsed(event.conv, '<i>{}, invited user {} without authorization!'.format(event.user.full_name, names))
            bot.send_message_parsed(event.conv, '<i>{}: Please leave this hangout and ask a moderator to add you. Thank you for your understanding.'.format(names))
