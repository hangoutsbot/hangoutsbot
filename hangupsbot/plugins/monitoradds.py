"""
Plugin for monitoring new adds to HOs and alerting if users were not added by an admin or mod.
Add mods to the config.json file either globally or on an individual HO basis.
Add a "watch_new_adds": true  parameter to individual HOs in the config.json file.

Author: @Riptides
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
        admins_list = bot.get_config_suboption(event.conv_id, 'admins')
        if event.user_id.chat_id in admins_list:
            return

        mods_list = bot.get_config_suboption(event.conv_id, 'mods')
        try:
            if event.user_id.chat_id in mods_list:
                return
        except TypeError:
            # The mods are likely not configured. Continuing...
            pass

        html = "<b>!!! WARNING !!!</b><br /><br />"
        html += "<i><b>{}</b> invited user <b>{}</b> without authorization.<br /><br />".format(event.user.full_name, names)
        html += "<i><b>{}</b>: Please leave this hangout and ask a moderator to add you. Thank you for your understanding.".format(names)

        bot.send_html_to_conversation(event.conv, html)
