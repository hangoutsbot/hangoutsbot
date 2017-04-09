# Original Author: kilr00y@esthar.net

import hangups

import plugins

from hangups.user import UserList

def _initialise(bot):
    plugins.register_user_command(["admins"])

def _get_adminlist(bot):
    return bot.get_config_option('admins')

def admins(bot,event,*args):
    admin_list=_get_adminlist(bot)
    text="<b><u>List of Admins</u></b><br />"
    for admin_id in admin_list:
        user_object = UserList.get_user(bot._user_list,(admin_id,admin_id))
        fullname=user_object.full_name
        text+="{} <br />".format(fullname)
    yield from bot.coro_send_message(event.conv,text)
