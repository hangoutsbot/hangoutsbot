"""
Plugin for monitoring if bot is added to a HO and report it to the bot admins.
Add a "botaddnotif_enable": true  parameter in the config.json file.

Author: @cd334
"""

import asyncio 
import logging
import hangups
import plugins

logger = logging.getLogger(__name__)

def _initialise(bot):
    plugins.register_handler(_handle_join_notify, type="membership")

@asyncio.coroutine
def _handle_join_notify(bot, event, command):
    if not event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        return
    
    bot_id = bot._user_list._self_user.id_
    
    if not bot_id in event.conv_event.participant_ids:
        return

    enable = bot.get_config_option("botaddnotif_enable")

    if not enable == True :
        return

    name = hangups.ui.utils.get_conv_name(event.conv, truncate=False)

    message = u'<b>%s</b> has added me to Hangout: <b>%s</b>' % (event.user.full_name, name)

    admin_list=bot.get_config_option('admins')
    for admin_id in admin_list:
        yield from bot.coro_send_to_user(admin_id, message)