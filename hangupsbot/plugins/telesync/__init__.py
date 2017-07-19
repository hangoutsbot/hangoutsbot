# A Sync plugin for Telegram and Hangouts

import aiohttp
import asyncio
import io
import logging
import os
import random
import re

import telepot.aio
import telepot.exception

from telepot.aio.loop import MessageLoop

import hangups

import plugins

from webbridge import ( WebFramework,
                        FakeEvent )

from .parsers import hangups_markdown_to_telegram


logger = logging.getLogger(__name__)


# prefix for profile sync registration, must be non-empty string
reg_code_prefix = "VERIFY"


ClientSession = aiohttp.ClientSession()

@asyncio.coroutine
def convert_online_mp4_to_gif(source_url, fallback_url=False):
    """experimental utility function to convert telegram mp4s back into gifs"""
    global ClientSession

    config = _telesync_config(tg_bot.ho_bot)

    if "convert-with-gifscom" in config and not config["convert-with-gifscom"]:
        # must be explicitly disabled
        return fallback_url or source_url

    if "convert-with-gifscom" in config and config["convert-with-gifscom"] is not True:
        # api key can be explicitly defined
        api_key = config["convert-with-gifscom"]
    else:
        # an api key isn't required, but...
        # XXX: demo api key from https://gifs.com/
        api_key = "gifs56d63999f0f34"

    # retrieve the source image
    api_request = yield from ClientSession.get(source_url)
    raw_image = yield from api_request.read()

    # upload it to gifs.com for conversion

    url = "https://api.gifs.com/media/upload"

    headers = { "Gifs-Api-Key": api_key }
    data = aiohttp.formdata.FormData()
    data.add_field('file', raw_image)
    data.add_field('title', 'example.mp4')

    response = yield from ClientSession.post(url, data=data, headers=headers)
    if response.status != 200:
        return fallback_url or source_url

    results = yield from response.json()
    if "success" not in results:
        return fallback_url or source_url

    # return the link to the converted file

    return results["success"]["files"]["gif"]


# TELEGRAM BOT

class TelegramBot(telepot.aio.Bot):
    def __init__(self, hangupsbot):
        self.config = hangupsbot.config.get_by_path(['telesync'])

        super().__init__(self.config['api_key'])

        if "bot_name" in hangupsbot.config.get_by_path(["telesync"]):
            self.name = hangupsbot.config.get_by_path(["telesync"])["bot_name"]
        else:
            self.name = "bot"

        self.commands = {}

        self.onMessageCallback = TelegramBot.on_message
        self.onPhotoCallback = TelegramBot.on_photo
        self.onStickerCallback = TelegramBot.on_sticker
        self.onUserJoinCallback = TelegramBot.on_user_join
        self.onUserLeaveCallback = TelegramBot.on_user_leave
        self.onLocationShareCallback = TelegramBot.on_location_share
        self.onSupergroupUpgradeCallback = TelegramBot.on_supergroup_upgrade

        self.ho_bot = hangupsbot
        self.chatbridge = BridgeInstance(hangupsbot, "telesync")

    @asyncio.coroutine
    def setup_bot_info(self):
        """Setup bot.id, bot.name and bot.username fields"""

        _bot_data = yield from self.getMe()

        self.id = _bot_data['id']
        self.name = _bot_data['first_name']
        self.username = _bot_data['username']

        logger.info("telepot bot - id: {}, name: {}, username: {}".format( self.id,
                                                                           self.name,
                                                                           self.username ))


    def add_command(self, cmd, func):
        self.commands[cmd] = func

    def remove_command(self, cmd):
        if cmd in self.commands:
            del self.commands[cmd]

    @staticmethod
    def is_command(msg):
        ho_bot_aliases = tuple(tg_bot.ho_bot.memory.get("bot.command_aliases") or [])
        if 'text' in msg:
            if( msg['text'].startswith('/')
                    and not msg['text'].startswith(ho_bot_aliases) ):
                return True
        return False

    @staticmethod
    def parse_command(cmd):
        txt_split = cmd.split()
        return txt_split[0].split("@")[0], txt_split[1:]

    @staticmethod
    def get_user_id(msg):
        if 'from' in msg:
            return str(msg['from']['id'])
        return ""

    @staticmethod
    def get_username(msg, chat_action='from'):
        if 'username' in msg[chat_action]:
            return str(msg[chat_action]['username'])
        return ""

    @staticmethod
    def on_message(bot, chat_id, msg):
        logger.info("unhandled message from {} with text {}".format(
            msg['from']['id'], msg['text'] ))

    @staticmethod
    def on_photo(bot, chat_id, msg):
        logger.info("unhandled photo from {} with metadata {}".format(
            msg['from']['id'], msg['photo'] ))

    @staticmethod
    def on_sticker(bot, chat_id, msg):
        logger.info("unhandled sticker from {} with metadata {}".format(
            msg['from']['id'], msg['sticker'] ))

    @staticmethod
    def on_user_join(bot, chat_id, msg):
        logger.info("unhandled new user {}".format(
            msg['new_chat_member']['first_name'] ))

    @staticmethod
    def on_user_leave(bot, chat_id, msg):
        logger.info("unhandled user exit {}".format(
            msg['left_chat_member']['first_name'] ))

    @staticmethod
    def on_location_share(bot, chat_id, msg):
        logger.info("unhandled location sharing from {}".format(
            msg['from']['first_name'] ))

    @staticmethod
    def on_supergroup_upgrade(bot, msg):
        logger.info("unhandled supergroup upgrade from uid {} to {}".format(
            msg['chat']['id'], msg['migrate_to_chat_id'] ))

    def set_on_message_callback(self, func):
        self.onMessageCallback = func

    def set_on_photo_callback(self, func):
        self.onPhotoCallback = func

    def set_on_sticker_callback(self, func):
        self.onStickerCallback = func

    def set_on_user_join_callback(self, func):
        self.onUserJoinCallback = func

    def set_on_user_leave_callback(self, func):
        self.onUserLeaveCallback = func

    def set_on_location_share_callback(self, func):
        self.onLocationShareCallback = func

    def set_on_supergroup_upgrade_callback(self, func):
        self.onSupergroupUpgradeCallback = func

    def is_telegram_admin(self, user_id):
        tg_conf = _telesync_config(self.ho_bot)
        if "admins" in tg_conf and user_id in tg_conf["admins"]:
            return True
        else:
            return False

    @asyncio.coroutine
    def get_hangouts_image_id_from_telegram_photo_id(self, photo_id, original_is_gif=False):
        metadata = yield from self.getFile(photo_id)
        file_path = metadata["file_path"]
        photo_path = "https://api.telegram.org/file/bot{}/{}".format(self.config['api_key'], file_path)
        logger.info("retrieving: {}".format(file_path))

        if file_path.endswith(".mp4") and original_is_gif:
            photo_path = yield from convert_online_mp4_to_gif(photo_path)

        try:
            ho_photo_id = yield from self.ho_bot.call_shared("image_upload_single", photo_path)
        except KeyError:
            # image plugin not loaded
            logger.warning("no shared hangoutsbot image upload, please add image plugin to your list of plugins")
            ho_photo_id = False

        return ho_photo_id

    @asyncio.coroutine
    def handle(self, msg):
        config = _telesync_config(tg_bot.ho_bot)

        if 'migrate_to_chat_id' in msg:
            yield from self.onSupergroupUpgradeCallback(self, msg)

        else:
            flavor = telepot.flavor(msg)
            if flavor == "chat":  # chat message
                content_type, chat_type, chat_id = telepot.glance(msg)
                if content_type == 'text':
                    if TelegramBot.is_command(msg):  # bot command
                        cmd, params = TelegramBot.parse_command(msg['text'])
                        user_id = TelegramBot.get_user_id(msg)
                        args = {'params': params, 'user_id': user_id, 'chat_type': chat_type}
                        if cmd in self.commands:
                            yield from self.commands[cmd](self, chat_id, args)
                        else:
                            if "be_quiet" in self.config and self.config["be_quiet"]:
                                pass
                            else:
                                yield from self.sendMessage(chat_id, "Unknown command: {cmd}".format(cmd=cmd))

                    else:  # plain text message
                        yield from self.onMessageCallback(self, chat_id, msg)

                elif content_type == 'location':
                    yield from self.onLocationShareCallback(self, chat_id, msg)

                elif content_type == 'new_chat_member':
                    yield from self.onUserJoinCallback(self, chat_id, msg)

                elif content_type == 'left_chat_member':
                    yield from self.onUserLeaveCallback(self, chat_id, msg)

                elif content_type == 'photo':
                    yield from self.onPhotoCallback(self, chat_id, msg)

                elif content_type == 'sticker':
                    yield from self.onStickerCallback(self, chat_id, msg)

                elif content_type == 'document':
                    if msg["document"]["mime_type"] == "image/gif":
                        # non-animated gif, treat like a photo
                        msg['photo'] = [ msg["document"] ]
                        msg['photo'][0]["width"] = 1 # XXX: required for tg_util_get_photo_list() sort
                        yield from self.onPhotoCallback(self, chat_id, msg)
                    elif msg["document"]["mime_type"] == "video/mp4":
                        logger.debug("received video/mp4 as a document: {}".format(msg))
                        # telegram converts animated gifs to mp4, upload is incompatible with hangouts
                        # treat like a photo anyway, hint to backend to resolve the issue
                        if "convert-with-gifscom" not in config or not config["convert-with-gifscom"]:
                            msg['photo'] = [ msg["document"]["thumb"] ]
                            yield from self.onPhotoCallback(self, chat_id, msg)
                        else:
                            msg['photo'] = [ msg["document"] ]
                            msg['photo'][0]["width"] = 1 # XXX: required for tg_util_get_photo_list() sort
                            yield from self.onPhotoCallback(self, chat_id, msg, original_is_gif=True)
                    elif msg["document"]["mime_type"].startswith("image/"):
                        # treat images like photos
                        msg['photo'] = [ msg["document"] ]
                        msg['photo'][0]["width"] = 1 # XXX: required for tg_util_get_photo_list() sort
                        yield from self.onPhotoCallback(self, chat_id, msg)
                    else:
                        logger.warning("unhandled document: {}".format(msg))
                else:
                    logger.warning("unhandled content type: {} {}".format(content_type, msg))

            elif flavor == "inline_query":  # inline query e.g. "@gif cute panda"
                query_id, from_id, query_string = telepot.glance(msg, flavor=flavor)
                logger.info("inline_query {}".format(msg))

            elif flavor == "chosen_inline_result":
                result_id, from_id, query_string = telepot.glance(msg, flavor=flavor)
                logger.info("chosen_inline_result {}".format(msg))

            else:
                raise telepot.BadFlavor(msg)


def tg_util_get_group_name(msg):
    """
    :param msg: msg object from telepot
    :return: if msg sent to a group, will return Groups name, return msg type otherwise
    """
    title = msg['chat']['type']
    # if title == 'group' or title == 'supergroup':
    if title in ['group', 'supergroup']:
        title = msg['chat']['title']
    return title

def tg_util_get_photo_caption(msg):
    caption = ""
    if 'caption' in msg:
        caption = msg['caption']

    return caption

def tg_util_get_photo_list(msg):
    photos = []
    if 'photo' in msg:
        photos = msg['photo']
        photos = sorted(photos, key=lambda k: k['width'])

    return photos

def tg_util_location_share_get_lat_long(msg):
    lat = ""
    long = ""
    if 'location' in msg:
        loc = msg['location']
        lat = loc['latitude']
        long = loc['longitude']

    return lat, long

def tg_util_create_gmaps_url(lat, long, https=True):
    return "{https}://maps.google.com/maps?q={lat},{long}".format(https='https' if https else 'http', lat=lat,
                                                                  long=long)

def tg_util_sync_get_user_name(msg, chat_action='from'):
    bot = tg_bot.ho_bot
    telesync_config = bot.get_config_option("telesync") or {}
    telegram_uid = str(msg['from']['id'])

    username = False

    fullname = _first_name = _last_name = ""
    if 'first_name' in msg[chat_action] and msg[chat_action]['first_name']:
        _first_name = msg[chat_action]['first_name']
    if 'last_name' in msg[chat_action] and msg[chat_action]['last_name']:
        _last_name = msg[chat_action]['last_name']
    if _first_name or _last_name:
        fullname = "{} {}".format(_first_name, _last_name).strip()

    if "prefer_fullname" in telesync_config and telesync_config["prefer_fullname"] and fullname:
        username = fullname
    elif 'username' in msg[chat_action]:
        username = msg[chat_action]['username']
    elif _first_name:
        username = _first_name
    elif _last_name:
        username = _last_name
    else:
        username = telegram_uid

    """linked profile support"""

    chat_id = False

    keys_tg_to_ho = ['profilesync', 'tg2ho', telegram_uid, 'chat_id']
    if bot.memory.exists(keys_tg_to_ho):
        chat_id = bot.memory.get_by_path(keys_tg_to_ho)

    else:
        """do it the legacy/half-broken way - old telesync didn't store chat_id, extract from link"""
        try:
            gplus = bot.memory.get_by_path(['profilesync', 'tg2ho', telegram_uid, 'user_gplus'])
            has_chat_id = re.search(r"/(\d+)/about", gplus)
            if has_chat_id:
                chat_id = has_chat_id.group(1)
        except (KeyError, TypeError):
            logger.info("unmapped/invalid hangouts user for {}".format(telegram_uid))

    if chat_id:
        # guaranteed full name
        hangups_user = bot.get_hangups_user(chat_id)
        full_name = hangups_user.full_name

        # determine if the hangoutsbot user has /setnickname
        nickname = False
        if bot.memory.exists(['user_data', chat_id, "nickname"]):
            nickname = bot.memory.get_by_path(['user_data', chat_id, "nickname"])

        if "prefer_fullname" in telesync_config and telesync_config["prefer_fullname"]:
            preferred_name = full_name
        elif nickname:
            preferred_name = nickname
        else:
            preferred_name = full_name

        # links with different visible content are no longer supported by hangouts clients
        username = preferred_name
        logger.info("mapped telegram id: {} to {}, {}".format(telegram_uid, chat_id, username))

    return username

@asyncio.coroutine
def tg_on_message(tg_bot, tg_chat_id, msg):
    # map telegram group id to hangouts group id
    tg_chat_id = str(tg_chat_id)
    tg2ho_dict = tg_bot.ho_bot.memory.get_by_path(['telesync'])['tg2ho']
    if tg_chat_id not in tg2ho_dict:
        return

    ho_conv_id = tg2ho_dict[tg_chat_id]
    user = tg_util_sync_get_user_name(msg)
    chat_title = tg_util_get_group_name(msg)

    config = _telesync_config(tg_bot.ho_bot)

    original_message = msg["text"]

    if 'sync_reply_to' in config and config['sync_reply_to'] and 'reply_to_message' in msg:
        """specialised formatting for reply-to telegram messages"""

        content_type, chat_type, chat_id = telepot.glance(msg['reply_to_message'])

        if msg['reply_to_message']['from']['first_name'].lower() == tg_bot.name.lower():
            r_text = ( msg['reply_to_message']['text'].split(':')
                       if 'text' in msg['reply_to_message'] else content_type )

            r2_user = r_text[0]
        else:
            r_text = ( ['', msg['reply_to_message']['text']]
                       if 'text' in msg['reply_to_message'] else content_type )

            r2_user = tg_util_sync_get_user_name(msg['reply_to_message'])

        if content_type == 'text':
            r2_text = r_text[1]
            r2_text = ( r2_text
                        if len(r2_text) < 30 else r2_text[0:30] + "..." )

        else:
            r2_text = content_type

        r2_format = "\n| **{}**\n| _{}_\n{}"
        original_message = r2_format.format(r2_user, r2_text, original_message)

    yield from tg_bot.chatbridge._send_to_internal_chat(
        ho_conv_id,
        original_message,
        {   "config": config,
            "source_user": user,
            "source_uid": msg['from']['id'],
            "source_title": chat_title })


@asyncio.coroutine
def tg_on_sticker(tg_bot, tg_chat_id, msg):
    tg2ho_dict = tg_bot.ho_bot.memory.get_by_path(['telesync'])['tg2ho']

    if str(tg_chat_id) in tg2ho_dict:
        config = _telesync_config(tg_bot.ho_bot)
        ho_conv_id = tg2ho_dict[str(tg_chat_id)]
        chat_title = tg_util_get_group_name(msg)
        user = tg_util_sync_get_user_name(msg)

        ho_photo_id = None
        if "enable_sticker_sync" in config and config["enable_sticker_sync"]:
            yield from tg_bot.chatbridge._send_to_internal_chat(
                ho_conv_id,
                "_uploading sticker from {} in {}_".format(user, chat_title),
                {   "config": config,
                    "source_user": user,
                    "source_uid": msg['from']['id'],
                    "source_title": chat_title })
            ho_photo_id = yield from tg_bot.get_hangouts_image_id_from_telegram_photo_id(msg['sticker']['file_id'])

        yield from tg_bot.chatbridge._send_to_internal_chat(
            ho_conv_id,
            "sent {} sticker".format(msg["sticker"]['emoji']),
            {   "config": config,
                "source_user": user,
                "source_uid": msg['from']['id'],
                "source_title": chat_title },
            image_id=ho_photo_id )
        logger.info("sticker posted to hangouts")


@asyncio.coroutine
def tg_on_photo(tg_bot, tg_chat_id, msg, original_is_gif=False):
    tg2ho_dict = tg_bot.ho_bot.memory.get_by_path(['telesync'])['tg2ho']

    if str(tg_chat_id) in tg2ho_dict:
        ho_conv_id = tg2ho_dict[str(tg_chat_id)]
        chat_title = tg_util_get_group_name(msg)

        config = _telesync_config(tg_bot.ho_bot)

        user = tg_util_sync_get_user_name(msg)

        text = "_uploading photo from {} in {}_".format(
            user,
            chat_title )

        yield from tg_bot.chatbridge._send_to_internal_chat(
            ho_conv_id,
            text,
            {   "config": config,
                "source_user": user,
                "source_uid": msg['from']['id'],
                "source_title": chat_title })

        tg_photos = tg_util_get_photo_list(msg)
        tg_photo_id = tg_photos[len(tg_photos) - 1]['file_id']
        ho_photo_id = yield from tg_bot.get_hangouts_image_id_from_telegram_photo_id(tg_photo_id,
                                                                                     original_is_gif=original_is_gif)

        if ho_photo_id:
            text = "sent a photo"
        else:
            text = "sent a photo, but telesync could not load it"

        yield from tg_bot.chatbridge._send_to_internal_chat(
            ho_conv_id,
            text,
            {   "config": config,
                "source_user": user,
                "source_uid": msg['from']['id'],
                "source_title": chat_title },
            image_id=ho_photo_id )

        logger.info("photo posted to hangouts")


@asyncio.coroutine
def tg_on_user_join(tg_bot, tg_chat_id, msg):
    config_dict = _telesync_config(tg_bot.ho_bot)
    if 'sync_join_messages' not in config_dict or not config_dict['sync_join_messages']:
        return

    tg2ho_dict = tg_bot.ho_bot.memory.get_by_path(['telesync'])['tg2ho']

    if str(tg_chat_id) in tg2ho_dict:
        ho_conv_id = tg2ho_dict[str(tg_chat_id)]
        chat_title = tg_util_get_group_name(msg)

        config = _telesync_config(tg_bot.ho_bot)

        formatted_line = "*{}* added **{}** to *{}*".format(
            tg_util_sync_get_user_name(msg, chat_action='new_chat_member'),
            ", ".join([ new_user["username"]
                        for new_user in msg["new_chat_members"] ]),
            chat_title )

        yield from tg_bot.chatbridge._send_to_internal_chat(
            ho_conv_id,
            formatted_line,
            {   "config": config,
                "source_user": "telesync",
                "source_uid": False,
                "source_title": chat_title })

        logger.info("join {} {}".format( ho_conv_id,
                                         formatted_line ))


@asyncio.coroutine
def tg_on_user_leave(tg_bot, tg_chat_id, msg):
    config_dict = _telesync_config(tg_bot.ho_bot)
    if 'sync_join_messages' not in config_dict or not config_dict['sync_join_messages']:
        return

    tg2ho_dict = tg_bot.ho_bot.memory.get_by_path(['telesync'])['tg2ho']

    if str(tg_chat_id) in tg2ho_dict:
        ho_conv_id = tg2ho_dict[str(tg_chat_id)]
        chat_title = tg_util_get_group_name(msg)

        config = _telesync_config(tg_bot.ho_bot)

        formatted_line = "**{}** left *{}*".format(
            msg["left_chat_member"]["username"],
            chat_title )

        yield from tg_bot.chatbridge._send_to_internal_chat(
            ho_conv_id,
            formatted_line,
            {   "config": config,
                "source_user": "telesync",
                "source_uid": False,
                "source_title": chat_title })

        logger.info("left {} {}".format( ho_conv_id,
                                         formatted_line ))


@asyncio.coroutine
def tg_on_location_share(tg_bot, tg_chat_id, msg):
    lat, long = tg_util_location_share_get_lat_long(msg)
    maps_url = tg_util_create_gmaps_url(lat, long)

    tg2ho_dict = tg_bot.ho_bot.memory.get_by_path(['telesync'])['tg2ho']
    config = _telesync_config(tg_bot.ho_bot)

    if str(tg_chat_id) in tg2ho_dict:
        ho_conv_id = tg2ho_dict[str(tg_chat_id)]
        chat_title = tg_util_get_group_name(msg)

        config = _telesync_config(tg_bot.ho_bot)

        user = tg_util_sync_get_user_name(msg)
        text = maps_url

        formatted_line = "<b>{}</b>: {}".format( user,
                                                 text )

        yield from tg_bot.chatbridge._send_to_internal_chat(
            ho_conv_id,
            formatted_line,
            {   "config": config,
                "source_user": "telesync",
                "source_uid": False,
                "source_title": chat_title })

        logger.info("location {} {}".format( ho_conv_id,
                                             text ))


@asyncio.coroutine
def tg_on_supergroup_upgrade(bot, msg):
    old_chat_id = str(msg['chat']['id'])
    new_chat_id = str(msg['migrate_to_chat_id'])

    memory = bot.ho_bot.memory.get_by_path(['telesync'])
    tg2ho_dict = memory['tg2ho']
    ho2tg_dict = memory['ho2tg']

    if old_chat_id in tg2ho_dict:

        ho_conv_id = tg2ho_dict[old_chat_id]
        ho2tg_dict[ho_conv_id] = new_chat_id
        tg2ho_dict[new_chat_id] = ho_conv_id

        del tg2ho_dict[old_chat_id]

        new_memory = {'tg2ho': tg2ho_dict, 'ho2tg': ho2tg_dict}
        bot.ho_bot.memory.set_by_path(['telesync'], new_memory)
        bot.ho_bot.memory.save()

        logger.info("SUPERGROUP: {} to {}".format( old_chat_id,
                                                   new_chat_id ))


@asyncio.coroutine
def tg_command_whoami(bot, chat_id, args):
    user_id = args['user_id']
    chat_type = args['chat_type']
    if 'private' == chat_type:
        yield from bot.sendMessage(chat_id, "Your Telegram user id: {user_id}".format(user_id=user_id))
    else:
        yield from bot.sendMessage(chat_id, "This command can only be used in private chats")


@asyncio.coroutine
def tg_command_whereami(bot, chat_id, args):
    user_id = args['user_id']
    if bot.is_telegram_admin(user_id):
        yield from bot.sendMessage(chat_id, "current group's id: '{chat_id}'".format(chat_id=chat_id))
    else:
        yield from bot.sendMessage(chat_id, "Only admins can do that")


@asyncio.coroutine
def tg_command_set_sync_ho(bot, chat_id, args):  # /setsyncho <hangout conv_id>
    user_id = args['user_id']
    params = args['params']

    if not bot.is_telegram_admin(user_id):
        yield from bot.sendMessage(chat_id, "Only admins can do that")
        return

    if len(params) != 1:
        yield from bot.sendMessage(chat_id, "Illegal or Missing arguments!!!")
        return

    memory = bot.ho_bot.memory.get_by_path(['telesync'])
    tg2ho_dict = memory['tg2ho']
    ho2tg_dict = memory['ho2tg']

    if str(chat_id) in tg2ho_dict:
        yield from bot.sendMessage(chat_id,
                                   "Sync target '{ho_conv_id}' already set".format(ho_conv_id=str(params[0])))

    else:
        tg2ho_dict[str(chat_id)] = str(params[0])
        ho2tg_dict[str(params[0])] = str(chat_id)

        new_memory = {'tg2ho': tg2ho_dict, 'ho2tg': ho2tg_dict}
        bot.ho_bot.memory.set_by_path(['telesync'], new_memory)
        bot.ho_bot.memory.save()

        yield from bot.sendMessage(chat_id, "Sync target set to '{ho_conv_id}''".format(ho_conv_id=str(params[0])))


@asyncio.coroutine
def tg_command_clear_sync_ho(bot, chat_id, args):
    user_id = args['user_id']
    if not bot.is_telegram_admin(user_id):
        yield from bot.sendMessage(chat_id, "Only admins can do that")
        return
    memory = bot.ho_bot.memory.get_by_path(['telesync'])
    tg2ho_dict = memory['tg2ho']
    ho2tg_dict = memory['ho2tg']

    if str(chat_id) in tg2ho_dict:
        ho_conv_id = tg2ho_dict[str(chat_id)]
        del tg2ho_dict[str(chat_id)]
        del ho2tg_dict[ho_conv_id]

    new_memory = {'tg2ho': tg2ho_dict, 'ho2tg': ho2tg_dict}
    bot.ho_bot.memory.set_by_path(['telesync'], new_memory)
    bot.ho_bot.memory.save()

    yield from bot.sendMessage(chat_id, "Sync target cleared")


@asyncio.coroutine
def tg_command_add_bot_admin(bot, chat_id, args):
    user_id = args['user_id']
    params = args['params']
    chat_type = args['chat_type']

    if 'private' != chat_type:
        yield from bot.sendMessage(chat_id, "This command must be invoked in private chat")
        return

    if not bot.is_telegram_admin(user_id):
        yield from bot.sendMessage(chat_id, "Only admins can do that")
        return

    if len(params) != 1:
        yield from bot.sendMessage(chat_id, "Illegal or Missing arguments!!!")
        return

    tg_conf = _telesync_config(bot.ho_bot)

    text = ""
    if str(params[0]) not in tg_conf['admins']:
        tg_conf['admins'].append(str(params[0]))
        bot.ho_bot.config.set_by_path(['telesync'], tg_conf)
        bot.ho_bot.config.save()
        text = "User added to admins"
    else:
        text = "User is already an admin"

    yield from bot.sendMessage(chat_id, text)


@asyncio.coroutine
def tg_command_remove_bot_admin(bot, chat_id, args):
    user_id = args['user_id']
    params = args['params']
    chat_type = args['chat_type']

    if 'private' != chat_type:
        yield from bot.sendMessage(chat_id, "This command must be invoked in private chat")
        return

    if not bot.is_telegram_admin(user_id):
        yield from bot.sendMessage(chat_id, "Only admins can do that")
        return

    if len(params) != 1:
        yield from bot.sendMessage(chat_id, "Illegal or Missing arguments!!!")
        return

    target_user = str(params[0])

    tg_conf = _telesync_config(bot.ho_bot)

    text = ""
    if target_user in tg_conf['admins']:
        tg_conf['admins'].remove(target_user)
        bot.ho_bot.config.set_by_path(['telesync'], tg_conf)
        bot.ho_bot.save()
        text = "User removed from admins"
    else:
        text = "User is not an admin"

    yield from bot.sendMessage(chat_id, text)


@asyncio.coroutine
def tg_command_tldr(bot, chat_id, args):
    params = args['params']

    tg2ho_dict = tg_bot.ho_bot.memory.get_by_path(['telesync'])['tg2ho']
    if str(chat_id) in tg2ho_dict:
        ho_conv_id = tg2ho_dict[str(chat_id)]
        tldr_args = {'params': params, 'conv_id': ho_conv_id}
        try:
            text = bot.ho_bot.call_shared("plugin_tldr_shared", bot.ho_bot, tldr_args)
            yield from bot.sendMessage(chat_id, text, parse_mode='HTML')
        except KeyError as ke:
            yield from bot.sendMessage(chat_id, "TLDR plugin is not active. KeyError: {e}".format(e=ke))
    elif str(chat_id) not in tg2ho_dict:
        ho_conv_id = str(chat_id)
        tldr_args = {'params': params, 'conv_id': ho_conv_id}
        try:
            text = bot.ho_bot.call_shared("plugin_tldr_shared", bot.ho_bot, tldr_args)
            yield from bot.sendMessage(chat_id, text, parse_mode='HTML')
        except KeyError as ke:
            yield from bot.sendMessage(chat_id, "TLDR plugin is not active. KeyError: {e}".format(e=ke))


@asyncio.coroutine
def tg_command_sync_profile(bot, chat_id, args):
    if 'private' != args['chat_type']:
        yield from bot.sendMessage(chat_id, "Comand must be run in private chat!")
        return

    telegram_uid = str(args['user_id'])
    hangoutsbot = bot.ho_bot

    tg2ho_dict = hangoutsbot.memory.get_by_path(['profilesync'])['tg2ho']
    ho2tg_dict = hangoutsbot.memory.get_by_path(['profilesync'])['ho2tg']

    if telegram_uid in tg2ho_dict:
        if isinstance(tg2ho_dict[telegram_uid], str):
            yield from bot.sendMessage(chat_id, "profile is not fully synced")
            del ho2tg_dict[tg2ho_dict[telegram_uid]] # remove old registration code
            logger.info("{} is waiting verification".format(telegram_uid))
        else:
            yield from bot.sendMessage(chat_id, "profile is already synced")
            logger.info("{} is synced to {}".format(telegram_uid, tg2ho_dict[telegram_uid]))
            return

    # generate/regenerate the registration code
    registration_code = "{}{}".format(reg_code_prefix, random.randint(0, 9223372036854775807))
    tg2ho_dict[telegram_uid] = registration_code
    ho2tg_dict[registration_code] = telegram_uid

    new_memory = {'tg2ho': tg2ho_dict, 'ho2tg': ho2tg_dict}
    hangoutsbot.memory.set_by_path(['profilesync'], new_memory)
    hangoutsbot.memory.save()

    yield from bot.sendMessage( chat_id,
                                "please paste the following code in a private hangout with the bot: "
                                    "/bot syncprofile {}".format(registration_code))


@asyncio.coroutine
def tg_command_unsync_profile(bot, chat_id, args):
    if 'private' != args['chat_type']:
        yield from bot.sendMessage(chat_id, "Comand must be run in private chat!")
        return

    telegram_uid = str(args['user_id'])
    hangoutsbot = bot.ho_bot

    tg2ho_dict = hangoutsbot.memory.get_by_path(['profilesync'])['tg2ho']
    ho2tg_dict = hangoutsbot.memory.get_by_path(['profilesync'])['ho2tg']

    if telegram_uid in tg2ho_dict:
        if isinstance(tg2ho_dict[telegram_uid], str):
            del ho2tg_dict[ tg2ho_dict[telegram_uid] ]
        else:
            _mapped = tg2ho_dict[telegram_uid]
            if "ho_id" in _mapped:
                ho_id = _mapped["ho_id"]
                del ho2tg_dict[ho_id]
            if "chat_id" in _mapped:
                hangouts_uid = _mapped["chat_id"]
                del ho2tg_dict[hangouts_uid]
            del tg2ho_dict[telegram_uid]

        new_memory = {'tg2ho': tg2ho_dict, 'ho2tg': ho2tg_dict}
        hangoutsbot.memory.set_by_path(['profilesync'], new_memory)
        hangoutsbot.memory.save()

        yield from bot.sendMessage(chat_id, "all profile references removed")
        logger.info("removed profile references for {}".format(telegram_uid))
    else:
        yield from bot.sendMessage(chat_id, "no profile found")


@asyncio.coroutine
def tg_command_get_me(bot, chat_id, args):
    """
    return Telegram Bot's id, name and username
    :param bot: TelegramBot object
    :param chat_id: chat id
    :param args: other args
    :return: None
    """
    user_id = args['user_id']
    chat_type = args['chat_type']
    if 'private' != chat_type:
        yield from bot.sendMessage(chat_id, "Comand must be run in private chat!")
        return

    if bot.is_telegram_admin(user_id):
        yield from bot.sendMessage(chat_id,
                                   "id: {id}, name: {name}, username: @{username}".format(id=bot.id, name=bot.name,
                                                                                          username=bot.username))
    else:
        yield from bot.sendMessage(chat_id, "Only admins can do that")


# TELEGRAM DEFINITIONS END

# HANGOUTSBOT

tg_bot = None

# (Chat) BridgeInstance

class BridgeInstance(WebFramework):
    def setup_plugin(self):
        self.plugin_name = "telegramTelesync"

    def load_configuration(self, configkey):
        # immediately halt configuration load if it isn't available
        telesync_config = _telesync_config(self.bot)
        if "enabled" not in telesync_config  or not telesync_config["enabled"]:
            return

        # telesync uses bot memory to store its internal locations
        self.configuration = { "config": telesync_config,
                               "memory": self.bot.get_memory_option(configkey) }

        return self.configuration

    def applicable_configuration(self, conv_id):
        """telesync configuration compatibility

        * only 1-to-1 linkages (telegram-ho) allowed
        * utilises memory to store linkages, config.json for global settings"""

        self.load_configuration(self.configkey)

        applicable_configurations = []
        ho2tg_dict = self.configuration["memory"]["ho2tg"]
        if conv_id in ho2tg_dict:
            # combine config.json and memory options to generate a dict
            config_clone = dict(self.configuration["config"])
            config_clone.update({ self.configkey: [ ho2tg_dict[conv_id] ],
                                  "hangouts": [ conv_id ] })
            applicable_configurations.append({ "trigger": conv_id,
                                               "config.json": config_clone })

        return applicable_configurations

    @asyncio.coroutine
    def _send_deferred_media(self, media_link, eid):
        if media_link.endswith((".gif", ".gifv", ".webm", ".mp4")):
            yield from tg_bot.sendDocument( eid,
                                            media_link )
        else:
            yield from tg_bot.sendPhoto( eid,
                                         media_link )

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        conv_id = config["trigger"]
        external_ids = config["config.json"][self.configkey]

        user = event.passthru["original_request"]["user"]
        message = event.passthru["original_request"]["message"]

        """migrated from telesync _on_hangouts_message():

        * by this point of execution, applicable_configuration() would have
            already filtered only relevant events
        * telesync configuration only allows 1-to-1 telegram-ho mappings, this
            migrated function supports multiple telegram groups anyway"""

        if not message:
            message = ""

        message = hangups_markdown_to_telegram(message)

        bridge_user = self._get_user_details(user, { "event": event })
        telesync_config = config['config.json']
        if "prefer_fullname" in telesync_config and telesync_config["prefer_fullname"]:
            username = bridge_user["full_name"]
        else:
            username = bridge_user["preferred_name"]
        if bridge_user["chat_id"]:
            # wrap linked profiles with a g+ link
            username = "[{1}](https://plus.google.com/u/0/{0}/about)".format( bridge_user["chat_id"],
                                                                              username )

        chat_title = format(self.bot.conversations.get_name(conv_id))

        if "chatbridge" in event.passthru and event.passthru["chatbridge"]["source_title"]:
            chat_title = event.passthru["chatbridge"]["source_title"]

        for eid in external_ids:

            divider = ":"

            """XXX: media sending:

            * if media link is already available, send it immediately
              * real events from google servers will have the medialink in event.conv_event.attachment
              * media link can also be added as part of the passthru
            * for events raised by other external chats, wait for the public link to become available
            """

            try:
                if "attachments" in event.passthru["original_request"] and event.passthru["original_request"]["attachments"]:
                    # automatically prioritise incoming events with attachments available
                    media_link = event.passthru["original_request"]["attachments"][0]
                    logger.info("media link in original request: {}".format(media_link))

                    yield from self._send_deferred_media(media_link, eid)
                    message = "shared media"
                    divider = ""

                elif isinstance(event, FakeEvent):
                    if( "image_id" in event.passthru["original_request"]
                            and event.passthru["original_request"]["image_id"] ):
                        # without media link, create a deferred post until a public media link becomes available
                        image_id = event.passthru["original_request"]["image_id"]
                        logger.info("wait for media link: {}".format(image_id))

                        loop = asyncio.get_event_loop()
                        task = loop.create_task(
                            self.bot._handlers.image_uri_from(
                                image_id,
                                self._send_deferred_media,
                                eid ))

                elif( hasattr(event, "conv_event")
                        and hasattr(event.conv_event, "attachments")
                        and len(event.conv_event.attachments) == 1 ):
                    # catch actual events with media link  but didn' go through the passthru

                    media_link = event.conv_event.attachments[0]
                    logger.info("media link in original event: {}".format(media_link))

                    yield from self._send_deferred_media(media_link, eid)
                    message = "shared media"
                    divider = ""

                """standard message relay"""

                if( "sync_chat_titles" not in config["config.json"]
                        or( config["config.json"]["sync_chat_titles"] and chat_title )):

                    formatted_text = "{} ({}){} {}".format( username,
                                                            chat_title,
                                                            divider,
                                                            message )
                else:
                    formatted_text = "{}{} {}".format( username,
                                                       divider,
                                                       message )

                logger.info("sending {}: {}".format(eid, formatted_text))
                yield from tg_bot.sendMessage( eid,
                                               formatted_text,
                                               parse_mode = 'Markdown',
                                               disable_web_page_preview = True )

            except telepot.exception.BotWasKickedError as exc:
                logger.error("telesync bot was kicked from the telegram chat id {}".format(eid))
                # continue processing the rest of the external chats
            except:
                raise

    def format_incoming_message(self, message, external_context):
        config = external_context["config"]
        source_user = external_context["source_user"]
        source_title = external_context["source_title"]

        if( "sync_chat_titles" not in config
                or( config["sync_chat_titles"] and source_title )):
            formatted = "<b>{}</b> ({}): {}".format( source_user,
                                                     source_title,
                                                     message )
        else:
            formatted = "<b>{}</b>: {}".format( source_user, message )

        return formatted

    def map_external_uid_with_hangups_user(self, source_uid, external_context):
        telegram_uid = str(source_uid)
        profilesync_keys = [ "profilesync", "tg2ho", telegram_uid ]

        hangups_user = False
        try:
            hangouts_map = self.bot.memory.get_by_path(profilesync_keys)

            if isinstance(hangouts_map, str):
                # security: sync is incomplete, should be a dict
                return False

            if "chat_id" in hangouts_map:
                hangouts_uid = hangouts_map["chat_id"]
            elif "user_gplus" in hangouts_map:
                # old semi-broken way
                gplus = hangouts_map["user_gplus"]
                has_chat_id = re.search(r"/(\d+)/about", gplus)
                if has_chat_id:
                    hangouts_uid = has_chat_id.group(1)
            else:
                hangouts_uid = False

            if hangouts_uid:
                _hangups_user = self.bot.get_hangups_user(hangouts_uid)
                if _hangups_user.definitionsource:
                    hangups_user = _hangups_user
        except KeyError:
            logger.info("no hangups user for {}".format(source_uid))

        return hangups_user


"""hangoutsbot plugin initialisation"""

def _initialise(bot):
    if not _telesync_config(bot):
        return

    if not bot.memory.exists(['telesync']):
        bot.memory.set_by_path(['telesync'], {'ho2tg': {}, 'tg2ho': {}})
        bot.memory.save()

    if not bot.memory.exists(['profilesync']):
        bot.memory.set_by_path(['profilesync'], {'ho2tg': {}, 'tg2ho': {}})
        bot.memory.save()

    global tg_bot

    tg_bot = TelegramBot(bot)

    tg_bot.set_on_message_callback(tg_on_message)
    tg_bot.set_on_photo_callback(tg_on_photo)
    tg_bot.set_on_sticker_callback(tg_on_sticker)
    tg_bot.set_on_user_join_callback(tg_on_user_join)
    tg_bot.set_on_user_leave_callback(tg_on_user_leave)
    tg_bot.set_on_location_share_callback(tg_on_location_share)
    tg_bot.set_on_supergroup_upgrade_callback(tg_on_supergroup_upgrade)
    tg_bot.add_command("/whoami", tg_command_whoami)
    tg_bot.add_command("/whereami", tg_command_whereami)
    tg_bot.add_command("/setsyncho", tg_command_set_sync_ho)
    tg_bot.add_command("/clearsyncho", tg_command_clear_sync_ho)
    tg_bot.add_command("/addadmin", tg_command_add_bot_admin)
    tg_bot.add_command("/removeadmin", tg_command_remove_bot_admin)
    tg_bot.add_command("/tldr", tg_command_tldr)
    tg_bot.add_command("/syncprofile", tg_command_sync_profile)
    tg_bot.add_command("/unsyncprofile", tg_command_unsync_profile)
    tg_bot.add_command("/getme", tg_command_get_me)

    plugins.start_asyncio_task(MessageLoop(tg_bot).run_forever())
    plugins.start_asyncio_task(tg_bot.setup_bot_info())

    plugins.register_admin_command(["telesync"])
    plugins.register_user_command(["syncprofile"])

    plugins.register_handler(_on_membership_change, type="membership")

def _telesync_config(bot):
    # immediately halt configuration load if it isn't available
    telesync_config = bot.get_config_option("telesync") or {}
    if "enabled" not in telesync_config  or not telesync_config["enabled"]:
        return False
    return telesync_config


def syncprofile(bot, event, *args):
    """link g+ and telegram profile together

    /bot syncprofile <id> - syncs the g+ profile with the telegram profile, id will be posted on telegram"""

    parameters = list(args)

    if len(parameters) != 1:
        yield from bot.coro_send_message(event.conv_id, "supply registration id as single parameter")

    else:
        registration_code = str(parameters[0])
        ho2tg_dict = bot.memory.get_by_path(['profilesync'])['ho2tg']
        tg2ho_dict = bot.memory.get_by_path(['profilesync'])['tg2ho']

        hangouts_uid = str(event.user_id.chat_id)

        if( hangouts_uid in ho2tg_dict
                and ho2tg_dict[hangouts_uid] in tg2ho_dict
                and not isinstance(tg2ho_dict[ho2tg_dict[hangouts_uid]], str) ):

            yield from bot.coro_send_message(
                event.conv_id,
                "profile is already synced" )

        elif not registration_code.startswith(reg_code_prefix):
            yield from bot.coro_send_message(
                event.conv_id,
                "execute /syncprofile command in a private chat with the bot on telegram first" )

        elif registration_code in ho2tg_dict:
            ho_id = registration_code
            telegram_uid = str(ho2tg_dict[registration_code])

            user_gplus = 'https://plus.google.com/u/0/{}/about'.format(hangouts_uid)

            tg2ho_dict[telegram_uid] = {
                'registration_code': registration_code,
                'chat_id': hangouts_uid,
                'user_gplus': user_gplus }
            ho2tg_dict[hangouts_uid] = telegram_uid

            del ho2tg_dict[registration_code]

            new_mem = {'tg2ho': tg2ho_dict, 'ho2tg': ho2tg_dict}
            bot.memory.set_by_path(['profilesync'], new_mem)
            bot.memory.save()

            yield from bot.coro_send_message(
                event.conv_id,
                "profile sync successfully set up" )
        else:
            yield from bot.coro_send_message(
                event.conv_id,
                "execute /syncprofile command in a private chat with the bot on telegram first" )


def telesync(bot, event, *args):
    """join abitrary hangouts and telegram groups together

    * /bot telesync <telegram chat id> - set sync with telegram group
    * /bot telesync - disable sync and clear sync data from memory"""

    parameters = list(args)
    conv_id = event.conv_id

    memory = bot.memory.get_by_path(['telesync'])
    tg2ho_dict = memory['tg2ho']
    ho2tg_dict = memory['ho2tg']

    if len(parameters) == 0:
        if conv_id in ho2tg_dict:
            tg_chat_id = ho2tg_dict[conv_id]

            del ho2tg_dict[conv_id]
            del tg2ho_dict[tg_chat_id]

            yield from bot.coro_send_message(
                conv_id,
                "telesync removed: {}-{}".format(
                    tg_chat_id, conv_id))
        else:
            logger.info('active telesyncs: {}'.format(memory))
            yield from bot.coro_send_message(
                conv_id,
                "telesync did nothing")

    elif len(parameters) == 1:
        tg_chat_id = parameters[0]

        if conv_id in ho2tg_dict:
            yield from bot.coro_send_message(
                conv_id,
                "telesync already active: {}-{}".format(
                    tg_chat_id, conv_id))
        else:
            tg2ho_dict[tg_chat_id] = conv_id
            ho2tg_dict[conv_id] = tg_chat_id

            yield from bot.coro_send_message(
                conv_id,
                "telesync activated: {}-{}".format(
                    tg_chat_id, conv_id))

    else:
        yield from bot.coro_send_message(conv_id, "too many arguments")

    new_memory = {'ho2tg': ho2tg_dict, 'tg2ho': tg2ho_dict}
    bot.memory.set_by_path(['telesync'], new_memory)
    bot.memory.save()


@asyncio.coroutine
def _on_membership_change(bot, event, command=""):
    config_dict = _telesync_config(bot)

    if 'sync_join_messages' not in config_dict or not config_dict['sync_join_messages']:
        return

    # Generate list of added or removed users
    event_users = [ event.conv.get_user(user_id)
                    for user_id in event.conv_event.participant_ids ]

    text = '_{}: {} {} {}_'.format(
        event.user.full_name,
        ', '.join([user.full_name for user in event_users]),
        "added to" if event.conv_event.type_ == hangups.MembershipChangeType.JOIN else "left",
        event.conv.name )

    ho2tg_dict = bot.memory.get_by_path(['telesync'])['ho2tg']
    if event.conv_id in ho2tg_dict:
        yield from tg_bot.sendMessage(
            ho2tg_dict[event.conv_id],
            text,
            parse_mode='Markdown',
            disable_web_page_preview=True )
