# A Sync plugin for Matrix and Hangouts

import os, logging
import io
import asyncio
import hangups
import plugins
import aiohttp
from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
from matrix_client.api import MatrixHttpApi
from requests.exceptions import MissingSchema
from handlers import handler
from commands import command
import random

logger = logging.getLogger(__name__)

matrix_bot = None
ho_bot = None
matrixsync_config = None
loop = None

def _initialise(bot):
    if not bot.config.exists(['matrixsync']):
        bot.config.set_by_path(['matrixsync'], {'homeserver': "PUT_YOUR_MATRIX_SERVER_ADDRESS_HERE",
                                              'username': "PUT_YOUR_BOT_USERNAME_HERE",
                                              'password': "PUT_YOUR_BOT_PASSWORD_HERE",
                                              'enabled': True,
                                              'admins': [],
                                              'be_quiet': False})

    bot.config.save()
    
    if not bot.memory.exists(['matrixsync']):
        bot.memory.set_by_path(['matrixsync'], {'ho2mx': {}, 'mx2ho': {}})

    bot.memory.save()
    global matrixsync_config
    matrixsync_config = bot.config.get_by_path(['matrixsync'])

    if matrixsync_config['enabled']:
        global ho_bot
        global matrix_bot
        global loop
        loop = asyncio.get_event_loop()
        ho_bot = bot
        ho_bot.logger = logger
        if "PUT_YOUR_MATRIX_SERVER_ADDRESS_HERE" not in matrixsync_config['homeserver']:
            matrix_bot = MatrixClient(matrixsync_config['homeserver'], valid_cert_check=False)
            try:
                matrix_bot.login_with_password(matrixsync_config['username'], matrixsync_config['password'])
                mx2ho_dict = ho_bot.memory.get_by_path(['matrixsync'])['mx2ho']
                for room_id in mx2ho_dict:
                    
                    room = matrix_bot.join_room(room_id)
                    room.add_listener(on_message)
                    matrix_bot.start_listener_thread()
                
                matrix_bot.add_invite_listener(autojoin)
            except MatrixRequestError as e:
                print(e)
                if e.code == 403:
                    print("Bad username or password.")
                else:
                    print("Check your sever details are correct.")
            except MissingSchema as e:
                print("Bad URL format.")
                print(e)


def mx_on_message(mx_chat_alias, msg, roomName, user, ho_bot, loop):
    mx2ho_dict = ho_bot.memory.get_by_path(['matrixsync'])['mx2ho']
    asyncio.set_event_loop(loop)
    local_loop = asyncio.get_event_loop()
    if mx_chat_alias in mx2ho_dict:
        x = "joined"
        if x in msg:
            text = msg
            ho_conv_id = mx2ho_dict[mx_chat_alias]
            asyncio.async(ho_bot.coro_send_message(ho_conv_id, text))
            ho_bot.logger.info("[MATRIXSYNC] Matrix user {user} joined synced to: {ho_conv_id}".format(user=user,
                                                                                                       ho_conv_id=ho_conv_id))
        else:
            text = "<b>{uname}</b> <b>({gname})</b>: {text}".format(uname=user,
                                                                    gname=roomName,
                                                                    text=msg)
            ho_conv_id = mx2ho_dict[mx_chat_alias]
            asyncio.async(ho_bot.coro_send_message(ho_conv_id, text))
            ho_bot.logger.info("[MATRIXSYNC] Matrix message forwarded: {msg} to: {ho_conv_id}".format(msg=msg,
                                                                                                      ho_conv_id=ho_conv_id))
    else:
        ho_bot.logger.info("wrong")

def on_message(self, event):
    global ho_bot
    global loop
    asyncio.set_event_loop(loop)
    local_loop = asyncio.get_event_loop()
    matrix_raw = matrix_bot.api
    if event['type'] == "m.room.member":
        if event['membership'] == "join":
            user_obj = matrix_bot.get_user(event['sender'])
            user = user_obj.get_display_name()
            roomName = matrix_raw.get_room_name(self.room_id)['name']
            msg = "{} joined".format(user)
            mx_on_message(self.room_id, msg, roomName, user, ho_bot, local_loop)
    elif event['type'] == "m.room.message":
        if event['content']['msgtype'] == "m.text":
            user_obj = matrix_bot.get_user(event['sender'])
            user = user_obj.get_display_name()
            roomName = matrix_raw.get_room_name(self.room_id)['name']
            msg = event['content']['body']
            mx_on_message(self.room_id, msg, roomName, user, ho_bot, local_loop)
    else:
        ho_bot.logger.info(event['type'])

        
def commands(self, event):
    global matrix_bot
    global ho_bot
    if event['type'] == "m.room.message":
        if event['content']['msgtype'] == "m.text":
            if event['content']['body'].startswith('/'):
                if "hosync" in event['content']['body']:
                    params = event['content']['body'].split('mango', 1)[1]
                    
                    if len(params) != 1:
                        matrix_bot.send_message(self.room_id, "Illegal or Missing arguments!!!", msgtype='m.text')
                        return

                    memory = ho_bot.memory.get_by_path(['matrixsync'])
                    mx2ho_dict = memory['mx2ho']
                    ho2mx_dict = memory['ho2mx']

                    if str(self.room_id) in mx2ho_dict:
                        matrix_bot.send_message(self.room_id, "Sync target '{mx_conv_id}' already set".format(mx_conv_id=str(params)), msgtype='m.text')
                    else:
                        mx2ho_dict[str(chat_id)] = str(params)
                        ho2mx_dict[str(params)] = str(chat_id)

                        new_memory = {'mx2ho': mx2ho_dict, 'ho2mx': ho2mx_dict}
                        ho_bot.memory.set_by_path(['matrixsync'], new_memory)

                        matrix_bot.send_message(self.room_id, "Sync target set to '{mx_conv_id}''".format(mx_conv_id=str(params)), msgtype='m.text')
        
def autojoin(self, room_id, event):
    try:
        room = matrix_bot.join_room(room_id)
        room.add_listener(commands)
        matrix_bot.start_listener_thread()
        
    except MatrixRequestError as e:
        print(e)
        if e.code == 400:
            print("Room ID/Alias in the wrong format")
        else:
            print("Couldn't find room.")
                
@command.register(admin=True)
def matrixsync(bot, event, *args):
    """
    /bot matrixsync <matrix chat alias> - set sync with matrix room
    /bot matrixsync - disable sync and clear sync data from memory
    """
    parameters = list(args)

    memory = bot.memory.get_by_path(['matrixsync'])
    mx2ho_dict = memory['mx2ho']
    ho2mx_dict = memory['ho2mx']

    if len(parameters) > 1:
        yield from bot.coro_send_message(event.conv_id, "Too many arguments")

    elif len(parameters) == 0:
        if str(event.conv_id) in ho2mx_dict:
            mx_chat_alias = ho2mx_dict[str(event.conv_id)]
            del ho2mx_dict[str(event.conv_id)]
            del mx2ho_dict[str(mx_chat_alias)]

        yield from bot.coro_send_message(event.conv_id, "Sync target cleared")

    elif len(parameters) == 1:
        mx_chat_alias = str(parameters[0])

        if str(event.conv_id) in ho2mx_dict:
            yield from bot.coro_send_message(event.conv_id,
                                             "Sync target '{mx_conv_alias}' already set".format(
                                                 mx_conv_alias=str(mx_chat_alias)))
        else:
            mx2ho_dict[str(mx_chat_alias)] = str(event.conv_id)
            ho2mx_dict[str(event.conv_id)] = str(mx_chat_alias)
            yield from bot.coro_send_message(event.conv_id,
                                             "Sync target set to {mx_conv_alias}".format(mx_conv_alias=str(mx_chat_alias)))

    else:
        raise RuntimeError("plugins/matrixsync: it seems something really went wrong, you should not see this error")

    new_memory = {'ho2mx': ho2mx_dict, 'mx2ho': mx2ho_dict}
    bot.memory.set_by_path(['matrixsync'], new_memory)

        
@asyncio.coroutine
def is_valid_image_link(url):
    """
    :param url:
    :return: result, file_name
    """
    if ' ' not in url:
        if url.startswith(("http://", "https://")):
            if url.endswith((".jpg", ".jpeg", ".gif", ".gifv", ".webm", ".png", ".mp4")):
                ext = url.split(".")[-1].strip()
                file = url.split("/")[-1].strip().replace(".", "").replace("_", "-")
                return True, "{name}.{ext}".format(name=file, ext=ext)
            else:
                with aiohttp.ClientSession() as session:
                    resp = yield from session.get(url)
                    headers = resp.headers
                    resp.close()
                    if "image" in headers['CONTENT-TYPE']:
                        content_disp = headers['CONTENT-DISPOSITION']
                        content_disp = content_disp.replace("\"", "").split("=")
                        file_ext = content_disp[2].split('.')[1].strip()
                        if file_ext in ("jpg", "jpeg", "gif", "gifv", "webm", "png", "mp4"):
                            file_name = content_disp[1].split("?")[0].strip()
                            return True, "{name}.{ext}".format(name=file_name, ext=file_ext)
    return False, ""

    
@handler.register(priority=5, event=hangups.ChatMessageEvent)
def _on_hangouts_message(bot, event, command=""):
    global matrix_bot

    if event.text.startswith('/'):  # don't sync /bot commands
        return

    sync_text = event.text
    photo_url = ""

    has_photo, photo_file_name = yield from is_valid_image_link(sync_text)

    if has_photo:
        photo_url = sync_text
        sync_text = "(shared an image)"

    ho2mx_dict = bot.memory.get_by_path(['matrixsync'])['ho2mx']

    if event.conv_id in ho2mx_dict:
        user_gplus = 'https://plus.google.com/u/0/{uid}/about'.format(uid=event.user_id.chat_id)
        text_plain = '{uname}: {text}'.format(uname=event.user.full_name, text=sync_text)
        text_html = '<a href="{user_gplus}">{uname}</a> <b>({gname})</b>: {text}'.format(uname=event.user.full_name, text=sync_text, user_gplus=user_gplus, gname=event.conv.name)
        matrix_bot.api.send_message_event(ho2mx_dict[event.conv_id], "m.room.message", {"msgtype": "m.text", "body": text_plain, "formatted_body": text_html,  "format": "org.matrix.custom.html"})

        if has_photo:
            logger.info("plugins/matrixsync: photo url: {url}".format(url=photo_url))
            matrix_bot.api.send_content(ho2mx_dict[event.conv_id], photo_url, photo_url.rsplit('/', 1)[-1], "m.image", None)
