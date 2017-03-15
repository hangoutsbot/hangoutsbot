"""Telepot async Bot enhanced"""

import asyncio
import html as html_module
import io
import logging
import os
import random
import string
import hangups_event
import telepot
import telepot.aio
import telepot.exception

logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:
    Image = None
    logger.warning('missing requirement for Sticker formating')

# character used to generate tokens for the profile sync
TOKEN_CHAR = list(string.ascii_uppercase + string.digits)

def util_html_bold(text):
    """get html bold repr of input

    Args:
        text: string

    Returns:
        string, html bold repr of input
    """
    if not len(text):
        return ''
    return '<b>{}</b>'.format(text)

class Received(object):
    """store received messages, index by message id and photo_id

    Args:
        tg_bot: TelegramBot instance
    """
    def __init__(self, tg_bot):
        self.tg_bot = tg_bot
        self._photos = {}
        self._text = {}
        self._photo_ids = {}
        self._sticker = {}

    @property
    def text(self):
        """return RAM and memory.json source, check 'store_messages' in config

        Returns:
            dict, RAM source if 'store_messages' is False
        """
        if self.tg_bot.config['store_messages']:
            return self.tg_bot.ho_bot.memory['telesync']['received']['text']
        else:
            return self._text

    @property
    def photos(self):
        """return RAM and memory.json source, check 'store_messages' in config

        Returns:
            dict, RAM source if 'store_messages' is False
        """
        if self.tg_bot.config['store_messages']:
            return self.tg_bot.ho_bot.memory['telesync']['received']['photos']
        else:
            return self._photos

    @property
    def photo_ids(self):
        """return RAM and memory.json source, check 'store_messages' in config

        Returns:
            dict, RAM source if 'store_messages' is False
        """
        if self.tg_bot.config['store_photoids']:
            return (
                self.tg_bot.ho_bot.memory['telesync']['received']['photo_ids']
                )
        else:
            return self._photo_ids

    @property
    def sticker(self):
        """return RAM and memory.json source, check 'store_messages' in config

        Returns:
            dict, RAM source if 'store_messages' is False
        """
        if self.tg_bot.config['store_photoids']:
            return self.tg_bot.ho_bot.memory['telesync']['received']['sticker']
        else:
            return self._sticker

    def init_chat_id(self, tg_chat_id):
        """ensure the existance of dicts for text and photos from provided chat

        Args:
            tg_chat_id: string, key for dicts
        """
        if tg_chat_id not in self.text:
            self.text[tg_chat_id] = {}
        if tg_chat_id not in self.photos:
            self.photos[tg_chat_id] = {}

    def get_photos(self, tg_chat_id, only_ids=False):
        """return photos from the tg_chat sorted by message_id

        use only_ids to get only the photo_ids

        Args:
            tg_chat_id: string

        Returns:
            list of tupel of strings: photo_id, message_id
        """
        if not tg_chat_id in self.photos or not len(self.photos[tg_chat_id]):
            return []

        # results in: item[0:1] if only_ids == True else item[0:2] for the list
        end = 1 + int(not only_ids)
        return [
            item[0:end] for item in sorted(
                self.photos[tg_chat_id].items(),
                key=lambda x: int(x[1])
                )
            ]

    def get_message_ids(self, tg_chat_id):
        """return the message_ids from the tg_chat sorted

        Args:
            tg_chat_id: string

        Returns:
            list of strings
        """
        if not tg_chat_id in self.text or not len(self.text[tg_chat_id]):
            return []
        return sorted(self.text[tg_chat_id].keys())

    def is_duplicate(self, msg):
        """check for existance of msg id and compare text

        Args:
            msg: Message instance

        Returns:
            True if id known and text matches, otherwise False
        """
        if msg.msg_id in self.text[msg.chat_id]:
            if msg.text == self.text[msg.chat_id][msg.msg_id]:
                return True
        return False

    def is_valid_update(self, tg_chat_id, text='', photo_id=None):
        """return weather text and photo were seen in the last n messages

        compare text with last n stored messages from chat
        compare = check weather every line of the text is in a stored message
        check if photo_id is in the last n photos from chat
        n is set in the config with 'c_filter_received_n'

        if photo_id found, compare also the text with the caption of this photo

        Args:
            tg_chat_id: string
            text: string
            photo_id: string

        Returns:
            tupel of 2 boolean, one for existance of text, one for the photo_id
        """
        check_text = []
        last_n = self.tg_bot.config['c_filter_received_n']
        if last_n < 1:
            return True, True
        if photo_id:
            if photo_id in self.get_photos(tg_chat_id, True)[-last_n:]:
                new_photo = False
                check_text.append(self.photos[tg_chat_id][photo_id])
            else:
                new_photo = True
        else:
            new_photo = False

        if text:
            new_text = True
            check_text += self.get_message_ids(tg_chat_id)[-last_n:]
            text_split = text.split('\n')
            for message_id in check_text:
                new_text = len(text_split)
                for line in text_split:
                    if line in self.text[tg_chat_id][message_id]:
                        new_text -= 1
                    else:
                        break

                if not new_text:
                    logger.info('full text match in %s', message_id)
                    break

        else:
            new_text = False

        return bool(new_text), new_photo

    @asyncio.coroutine
    def periodic_cleanup(self, bot):
        """remove all messages and photo_ids that are no more needed

        keep last n photos from each chat
        keep last m messages from chat
        with keeping the captions (messages) from the last n photos,
            m is n plus a few messages, we keep at max n+n messages if n
                messages passed since the last photo

            n is max of
                config entry 'c_filter_received_n'
                config entry 'track_edits'

        sleep for x seconds after each run

            x is set in the config with 'sleep_after_clean_up'

        Args:
            bot: hangupsbot instance
        """
        tg_bot = self.tg_bot
        while bot.config.exists(['telesync', 'sleep_after_clean_up']):
            yield from asyncio.sleep(
                bot.config.get_by_path(
                    ['telesync', 'sleep_after_clean_up']
                    )
                )
            keep_n = max(
                tg_bot.config['c_filter_received_n'],
                tg_bot.config['track_edits']
                )
            changed = False
            # use copy as the dict should not change during the iteration
            for tg_chat_id in bot.memory.get_by_path(
                    ['telesync', 'tg_data']
                ).copy():
                photos_changed = True
                sorted_photo_data = self.get_photos(tg_chat_id)
                # remove not needed photo_ids and their caption
                for photo_id, message_id in sorted_photo_data[:-keep_n]:
                    self.text[tg_chat_id].pop(message_id, None)
                    self.photos[tg_chat_id].pop(photo_id, None)
                else:
                    photos_changed = False

                # create subset of (all messages) - (photo captions to keep)
                # remove all except the last n items
                messages_to_remove = sorted(
                    set(self.get_message_ids(tg_chat_id))
                    - set(self.get_photos(tg_chat_id, True)[-keep_n:])
                    )[:-keep_n]
                text_changed = True
                for message_id in messages_to_remove:
                    self.text[tg_chat_id].pop(message_id, None)
                else:
                    text_changed = False
                changed = photos_changed or text_changed or changed

            if changed and (
                    self.tg_bot.config['store_messages'] or \
                    self.tg_bot.config['store_messages']
                ):
                bot.memory.force_taint()
                bot.memory.save()


class User(object):
    """init user based on dict entry chat_action,

    use first_name from tg or full_name via profilesync from g+

    Args:
        msg: Message instance or message dict
        chat_action: target to pick user from, is key in msg
    """
    # Fallback for Telegram-channel with redacted publishers
    FALLBACK = {
        'id': 0,
        'first_name': '~'
    }
    bot = None

    def __init__(self, msg, chat_action='from'):
        if chat_action not in msg:
            msg[chat_action] = self.FALLBACK
        self.usr_id = str(msg[chat_action]['id'])
        self.name = str(msg[chat_action]['first_name'])
        self.has_username = 'username' in msg[chat_action]
        if self.has_username:
            self.username = str(msg[chat_action]['username'])

            if self.bot.memory.exists(
                    ['telesync', 'profilesync', 'usernames', self.usr_id]
                ):
                if self.bot.memory.get_by_path(
                        ['telesync', 'profilesync', 'usernames', self.usr_id]
                    ) != self.username:
                    self.bot.memory.set_by_path(
                        ['telesync', 'profilesync', 'usernames', self.usr_id],
                        self.username
                        )
                    # no need to force a dump
            else:
                self.bot.memory.set_by_path(
                    ['telesync', 'profilesync', 'usernames', self.usr_id],
                    self.username
                    )
                # no need to force a dump

        self.ho_user_id = 0
        if self.bot.memory.exists(
                ['telesync', 'profilesync', 'tg2ho', self.usr_id]
            ):
            self.ho_user_id = self.bot.memory.get_by_path(
                ['telesync', 'profilesync', 'tg2ho', self.usr_id]
                )
            self.name = self.bot.get_hangups_user(
                self.ho_user_id
                ).full_name

    def get_user_link(self):
        """create a tg-link from username or return firstname

        Returns:
            string, link to user or firstname
        """
        if not self.has_username:
            return self.name
        return "<a href='https://t.me/{uname}'>{name}</a>".format(
            name=self.username,
            uname=self.name
            )


class Message(object):
    """parse the message once

    keep value accessing via dict

    Args:
        msg: dict from telepot
    """
    bot = None

    def __init__(self, msg):
        self.msg = msg
        self.content_type, self.chat_type, self.chat_id = telepot.glance(msg)
        self.chat_id = str(self.chat_id)
        self.msg_id = str(msg['message_id'])
        self.reply = 'reply_to_message' in msg
        if self.reply:
            self.reply = Message(msg['reply_to_message'])
        self.user = User(msg)
        self.set_text()

    def __getitem__(self, key):
        return self.msg[key]

    def __iter__(self):
        return iter(self.msg)

    def __len__(self):
        return len(self.msg)

    def keys(self):
        """forward call"""
        return self.msg.keys()

    def is_command(self):
        """return weather text starts with /

        Returns:
            boolean
        """
        return self.text.startswith('/')

    def create_gmaps_url(self):
        """create Google Maps query from latitude and longitude in message

        Returns:
            string, a google maps link or default .content_type
        """
        lat = ''
        lng = ''
        if 'location' in self.msg:
            location = self.msg['location']
            if 'latitude' in location:
                lat = location['latitude']
            if 'longitude' in location:
                lng = location['longitude']
        if lat and lng:
            return 'https://maps.google.com/maps?q={lat},{lng}'.format(
                lat=lat,
                lng=lng
                )
        return self.content_type

    def get_group_name(self, show=False):
        """return chat name or chat type

        Returns:
            string: chat type if not a group/super/channel, otherwise the title
        """
        if not show:
            return ''
        gname = self.chat_type
        if self.chat_type in ['group', 'supergroup', 'channel']:
            gname = self['chat']['title']
        return util_html_bold(gname)

    def get_photo_caption(self):
        """get caption entry or empty string

        Returns:
            string
        """
        if 'caption' in self.msg:
            return self.msg['caption']
        return ''

    def get_photo_id(self):
        """return the photo id with the photo with max width

        Args:
            msg: Message instance

        Returns:
            string, photo_id of largest photo
        """
        sorted_photos = sorted(self.msg['photo'], key=lambda k: k['width'])
        return sorted_photos[- 1]['file_id']

    def get_sync_text(self, ho_conv_id):
        """return text for Hangouts formated: Name{SEPARATOR}Text

        Args:
            ho_conv_id: string, target for the message

        Returns:
            string
        """
        title = self.get_group_name(
            show=self.bot.get_config_suboption(ho_conv_id, 'sync_chat_titles')
            )
        if title:
            title = '({})'.format(title)
        template = self.bot.get_config_suboption(
            ho_conv_id,
            'sync_format_message'
            )
        return template.format(
            name=util_html_bold(self.user.name),
            title=title,
            separator=TelegramBot.SEPARATOR,
            text=self.text
            )

    def set_text(self):
        """map content_type to propper message text"""
        if self.content_type == 'text':
            self.text = self.msg['text']
        elif self.content_type == 'photo':
            # with extra space, will be stripped later on
            self.text = _('[Photo]') + ' '
            caption = self.get_photo_caption()
            # remove a synced photo tag
            caption = caption.replace(self.text.strip(), '', 1)
            separator = TelegramBot.SEPARATOR
            if separator in caption:
                name, caption = caption.partition(separator)[0:3:2]
                self.text = name + separator + self.text + caption
                return
            self.text = (self.text + caption).strip()
        elif self.content_type == 'sticker':
            self.text = _('[Sticker]')
        elif self.content_type == 'location':
            self.text = self.create_gmaps_url()
        else:
            self.text = '[{}]'.format(self.content_type)


class TelegramBot(telepot.aio.Bot):
    """enhanced telepot bot with Hangouts sync

    Args:
        ho_bot: hangupsbot instance
    """
    # info to class variable SEPARATOR:
    # used in sync messages to split sender from text, set this value in config:
    # key 'global_sync_separator' in config.json
    # also used to identify sync messages, so don't use a single letter one!
    # With changing it you will break parsing of recent chat messages
    SEPARATOR = ' : '

    # default path to store pictures for the download, can be set in config
    # key 'photo_path' in config.json
    PHOTO_PATH = '/tmp/telesync_photos_{botname}'

    # in MB, assume the max filesize of a picture is 10MB
    MIN_FREE_SPACE = 10

    def __init__(self, ho_bot):
        self.ho_bot = ho_bot
        TelegramBot.SEPARATOR = ho_bot.config['global_sync_separator']
        Message.bot = ho_bot
        User.bot = ho_bot
        try:
            super(TelegramBot, self).__init__(self.config['api_key'])
        except:
            raise telepot.TelegramError(_("Couldn't initialize telesync"), 10)
        self.ho_bot = ho_bot
        self._commands = {}
        self.loop_task = None
        self.received = Received(self)
        self.sending = 0
        self.user = None

    @asyncio.coroutine
    def start(self, bot=None):
        """setup bot user, init commands, set photo path, start message_loop

        Args:
            bot: unused, but needed for plugin coro start
        """
        bot_user = yield from self.getMe()
        self.user = User(
            {
                'bot': bot_user
            },
            chat_action='bot'
            )
        logger.info(
            '[TELESYNC] Botuser: id: %s, name: %s, username: %s',
            self.user.usr_id,
            self.user.name,
            self.user.username
            )
        self._add_command('/whoami', self._command_whoami)
        self._add_command('/whereami', self._command_whereami)
        self._add_command('/setsyncho', self._command_set_sync_ho)
        self._add_command('/clearsyncho', self._command_clear_sync_ho)
        self._add_command('/addadmin', self._command_add_admin)
        self._add_command('/removeadmin', self._command_remove_admin)
        self._add_command('/tldr', self._command_tldr)
        self._add_command('/syncprofile', self._command_sync_profile)
        self._add_command('/unsyncprofile', self._command_unsync_profile)
        self._add_command('/getme', self._command_get_me)
        self._add_command('/echo', self._command_echo)
        self._add_command('/getadmins', self._command_get_admins)
        self._add_command('/leave', self._command_leave)
        yield from self.update_photo_path()
        yield from self.message_loop()

    @property
    def config(self):
        """get telegram config

        Returns:
            dict, hangupsbot config entry for telegram
        """
        return self.ho_bot.config['telesync']

    @asyncio.coroutine
    def update_photo_path(self):
        """set the base path for downloads, try multiple locations

        priority:
            path in config
            plugins folder
            ~/.telesync_photos
            /tmp/telesync_photos_BOTNAME

        Returns:
            boolean, True if one of the paths is writable and has free diskspace
        """
        paths = []
        config_path = self.config['photo_path']
        if len(config_path):
            paths.append(config_path)
        for path in [
                os.path.dirname(os.path.realpath(__file__)) + '/',
                '~/',
                '/tmp/'
            ]:
            paths.append(path + 'telesync_photos/{botname}')
        for path in paths:
            formated_path = path.format(botname=self.user.name)
            if not os.path.exists(formated_path):
                try:
                    os.makedirs(formated_path, exist_ok=True)
                except PermissionError:
                    continue
            if not os.access(formated_path, os.W_OK):
                continue

            # check diskspace at current path/mount point
            disk = os.statvfs(formated_path)
            if (disk.f_bsize*disk.f_bfree/2**20) > TelegramBot.MIN_FREE_SPACE:
                TelegramBot.PHOTO_PATH = path
                return True

        logger.warning(
            _(
                'no photo_path is available, check permissions! at least one '
                'of the following paths should be writable to the bot user %s'
                ),
            paths
            )
        return False

    def _add_command(self, cmd, func):
        """setup command

        Args:
            cmd: string, command call
            func: method, to run on command
        """
        self._commands[cmd] = func

    def _remove_command(self, cmd):
        """unset command

        Args:
            cmd: string, key in self._commands
        """
        self._commands.pop(cmd, None)

    @asyncio.coroutine
    def periodic_profilesync_reminder(self, bot):
        """remind users to finish pending profilesyncs

        sleep for x hours after each notify run
        x determined by config entry 'profilesync_reminder'

        Args:
            bot: hangupsbot instance
        """
        while 'profilesync_reminder' in self.config:
            # to prevent spam on reboots, rather sleep before notify users
            yield from asyncio.sleep(
                3600 * self.config['profilesync_reminder']
                )
            for chat_id in bot.memory.get_by_path(
                    ['telesync', 'profilesync', 'pending_tg']
                ).copy():
                if self.loop_task:
                    yield from self._profilesync_info(
                        chat_id,
                        is_reminder=True
                        )

    @asyncio.coroutine
    def send_html(self, tg_chat_id, html):
        """send html to tg_chat_id

        Args:
            tg_chat_id: int, a chat the bot user has access to
            html: string, nested html tags are not allowed
        """
        # Bad Request: can\'t parse message text: Unsupported start tag "br/"
        html = html.replace('<br />', '\n')
        # Bad Request: can\'t parse message text: Unsupported start tag "u"
        html = html.replace('<u>', '<i>').replace('</u>', '</i>')
        try:
            yield from self.sendMessage(
                tg_chat_id,
                html,
                parse_mode='HTML',
                disable_web_page_preview=True
                )
        except telepot.exception.TelegramError:
            yield from self.sendMessage(
                tg_chat_id,
                html_module.escape(html),
                parse_mode='HTML',
                disable_web_page_preview=True
                )

    @asyncio.coroutine
    def _get_ho_photo_id(self, photo_id, target):
        """get known upload id for photo_id or download and upload the file

        after the upload remove the file as configured and store the id
        for target 'sticker' we remove the background and resize the image

        Args:
            photo_id: string
            target: string, 'sticker' or 'photo_ids'

        Returns:
            string, the known or new ho_photo_id
        """
        # access dicts at self.received.{photo_ids, sticker}
        if photo_id in getattr(self.received, target):
            cached_id = getattr(self.received, target)[photo_id]
            logger.info(
                '[TELESYNC] using cached id %s for %s',
                cached_id,
                photo_id
                )
            return cached_id

        # verify an existing location for downloading the photos
        if not os.path.exists(TelegramBot.PHOTO_PATH):
            if not self.update_photo_path():
                # no photo_path available, fallback to in memory handling
                self.config['do_not_keep_photos'] = True

        photo_path = (TelegramBot.PHOTO_PATH + '/{photo_id}{ext}').format(
            botname=self.user.name,
            photo_id=photo_id,
            ext='.webm' if target == 'sticker' else '.jpg'
            )

        photo_file = None
        if self.config['do_not_keep_photos']:
            photo_file = io.BytesIO()
            yield from self.download_file(photo_id, photo_file)
        else:
            yield from self.download_file(photo_id, photo_path)

        if target == 'sticker':
            photo_path, photo_file = self._util_edit_sticker(
                photo_path,
                photo_file
                )

        if self.config['do_not_keep_photos']:
            with io.BytesIO(photo_file.getvalue()) as photo_file_not_eof:
                ho_photo_id = yield from self.ho_bot._client.upload_image(
                    photo_file_not_eof,
                    filename=os.path.basename(photo_path)
                    )
            photo_file.close()
        else:
            with open(photo_path, 'rb') as photo_file:
                ho_photo_id = yield from self.ho_bot._client.upload_image(
                    photo_file,
                    filename=os.path.basename(photo_path)
                    )

        getattr(self.received, target)[photo_id] = ho_photo_id
        return ho_photo_id

    def _parse_command(self, msg):
        """get cmd and assigned bot_name

        valid pattern:
        /command
        /command args
        /command@name_bot args

        Args:
            msg: Message
        Returns:
            tupel of bool and 2 strings: command valid, command, args
        """
        if not msg.is_command():
            return False, '', ''
        txt_split = msg.text.split()
        cmd, is_addressed, name = txt_split[0].partition('@')
        if is_addressed:
            if name.lower() != self.user.username.lower():
                return False, '', ''
        return cmd in self._commands, cmd, txt_split[1:]

    def _util_edit_sticker(self, photo_path, photo_file):
        """remove background and resize the sticker, output as PNG

        Args:
            photo_path: string, path to the photo_file if not storing in RAM
            photo_file: BytesIO instance if using RAM
        """
        if Image is None:
            # module not loaded
            return photo_path, photo_file

        if photo_file is not None:
            image = Image.open(photo_file)
        else:
            image = Image.open(photo_path)
        max_size = self.config['sticker_max_size']
        if image.height > max_size:
            image = image.resize(
                (int(image.width/(image.height/max_size)), max_size)
                )
        if image.width > max_size:
            image = image.resize(
                (max_size, int(image.height/(image.width/max_size)))
                )

        if photo_file is not None:
            photo_file = io.BytesIO()
            image.save(photo_file, 'png')
        else:
            os.remove(photo_path)
            image.save(photo_path + '.png', 'png')
        photo_path = photo_path + '.png'
        image.close()
        return photo_path, photo_file

    def _util_format_reply(self, msg, new_text, ho_conv_id):
        """format the reply text and the new text

        default out: | <i><b>Username:</b></i>\n| <i>replytext</i>\nnew text
        channel out: | <i>replytext</i>\nnew text

        replytext is limited to x char by config for default or channel

        Args:
            msg: Message instance
            new_text: string, new message
            ho_conv_id: string, target conversation
        """
        if msg['chat']['type'] != 'channel':
            sync_proof = TelegramBot.SEPARATOR in msg.reply.text
            if msg.reply.user.usr_id == self.user.usr_id and sync_proof:
                r_user = msg.reply.text.partition(TelegramBot.SEPARATOR)[0]
                r_text = msg.reply.text.partition(TelegramBot.SEPARATOR)[2]
            else:
                r_user = msg.reply.user.name
                r_text = msg.reply.text
            sender = '| <i>{}</i> :\n'.format(util_html_bold(r_user))
            limit = self.ho_bot.get_config_suboption(
                ho_conv_id,
                'sync_reply_limit'
                )
        else:
            r_text = msg.reply.text
            sender = ''
            limit = self.ho_bot.get_config_suboption(
                ho_conv_id,
                'sync_reply_limit_tg-channel'
                )

        r_text = r_text if len(r_text) < limit else r_text[0:limit] + '...'
        return '{sender}| <i>{r_text}</i>\n{new_text}'.format(
            sender=sender,
            r_text=r_text,
            new_text=new_text
            )

    @asyncio.coroutine
    def handle(self, msg):
        """check event type and route message to target functions

        only process event type 'chat'

        Args:
            msg: dict, message from telepot
        """
        if 'migrate_to_chat_id' in msg:
            self._on_supergroup_upgrade(msg)
            return

        flavor = telepot.flavor(msg)

        if flavor != 'chat':
            logger.debug(
                "[TELESYNC] event is not a chat: '%s'",
                flavor
                )
            return

        msg = Message(msg)

        content_type = msg.content_type

        self.received.init_chat_id(msg.chat_id)

        if content_type == 'text':
            if self.received.is_duplicate(msg):
                return
            valid, cmd, params = self._parse_command(msg)
            if valid:
                # backwards compatibility
                args = {
                    'params': params,
                    'user_id': int(msg.user.usr_id),
                    'chat_type': msg.chat_type,
                    'msg': msg
                }
                yield from self._commands[cmd](int(msg.chat_id), args)
                return

            yield from self._on_message(msg)

            self.received.text[msg.chat_id][msg.msg_id] = msg.text

        elif content_type == 'location':
            yield from self._on_location_share(msg)

        elif content_type == 'new_chat_member':
            yield from self._on_user_join(msg)

        elif content_type == 'left_chat_member':
            yield from self._on_user_leave(msg)

        elif content_type == 'photo':
            yield from self._on_photo(msg)

        elif content_type == 'sticker':
            yield from self._on_sticker(msg)

        else:
            logger.debug(
                '[TELESYNC] not handeled content_type %s',
                repr(content_type)
                )

    @asyncio.coroutine
    def _on_message(self, msg):
        """message handler

        Args:
            msg: Message instance
        """
        bot = self.ho_bot
        chat_id = msg.chat_id
        run_command = False
        if bot.memory.exists(['telesync', 'tg2ho', chat_id]):
            ho_conv_id = bot.memory.get_by_path(['telesync', 'tg2ho', chat_id])

            if not bot.memory.exists(['telesync', 'tg_data', chat_id, 'user']):
                bot.memory.set_by_path(
                    ['telesync', 'tg_data', chat_id],
                    {'user': {}}
                    )
                # use dict to store ids for faster lookups and deletions
                # dump in the next part

            if not bot.memory.exists(
                    ['telesync', 'tg_data', chat_id, 'user', msg.user.usr_id]
                ):
                bot.memory.set_by_path(
                    ['telesync', 'tg_data', chat_id, 'user', msg.user.usr_id],
                    1
                    )
                bot.memory.save()

            if msg.user.ho_user_id:
                if msg.text.split()[0] in bot.memory['bot.command_aliases']:
                    fake_event = hangups_event.FakeEvent(
                        bot=self.ho_bot,
                        conv_id=ho_conv_id,
                        user_id=msg.user.ho_user_id,
                        text=msg.text
                        )
                    run_command = True

            text = msg.get_sync_text(ho_conv_id)

        elif bot.memory.exists(['telesync', 'channel2ho', chat_id]):
            if not self.received.is_valid_update(chat_id, text=msg.text)[0]:
                return
            ho_conv_id = bot.memory.get_by_path(
                ['telesync', 'channel2ho', chat_id]
                )
            text = msg.text
        else:
            # no sync target set for this chat
            return

        if msg.reply and self.config['sync_reply_to']:
            text = self._util_format_reply(msg, text, ho_conv_id)

        if msg.msg_id in self.received.text[msg.chat_id]:
            text = '<i>{update}:</i><br />{text}'.format(
                update=util_html_bold(self.config['update_label']),
                text=text
                )

        logger.info(
            '[TELESYNC] forwarding message from TG: %s to HO: %s',
            msg.chat_id,
            ho_conv_id
            )
        self.sending += 1
        yield from bot.coro_send_message(ho_conv_id, text)

        if run_command:
            asyncio.ensure_future(bot._handlers.handle_command(fake_event))

    @asyncio.coroutine
    def _on_photo(self, msg):
        """forward photo to channel or group if sync is set for tg_chat_id

        Args:
            msg: Message instance
        """
        bot = self.ho_bot

        if bot.memory.exists(['telesync', 'tg2ho', msg.chat_id]):
            ho_conv_id = bot.memory.get_by_path(
                ['telesync', 'tg2ho', msg.chat_id]
                )
            raw_caption = msg.get_photo_caption()

            photo_caption = msg.get_sync_text(ho_conv_id)

            photo_id = msg.get_photo_id()
            new_text = True
            new_photo = msg.msg_id not in self.received.get_message_ids(
                msg.chat_id
                )

        elif bot.memory.exists(['telesync', 'channel2ho', msg.chat_id]):
            ho_conv_id = bot.memory.get_by_path(
                ['telesync', 'channel2ho', msg.chat_id]
                )

            photo_caption = raw_caption = msg.get_photo_caption()

            photo_id = msg.get_photo_id()

            new_text, new_photo = self.received.is_valid_update(
                msg.chat_id,
                text=raw_caption,
                photo_id=photo_id
                )
        else:
            # no sync target set for this chat
            return

        if msg.msg_id in self.received.text[msg.chat_id]:
            photo_caption = '<i>{update}:</i><br />{text}'.format(
                update=util_html_bold(self.config['update_label']),
                text=photo_caption
                )

        self.received.text[msg.chat_id][msg.msg_id] = raw_caption

        if new_photo:
            ho_photo_id = yield from self._get_ho_photo_id(
                photo_id,
                'photo_ids'
                )
            self.received.photos[msg.chat_id][photo_id] = msg.msg_id

            logger.info(
                '[TELESYNC] forwarding photo from TG: %s to HO: %s',
                msg.chat_id,
                ho_conv_id
                )
            self.sending += 1
            yield from bot.coro_send_message(
                ho_conv_id,
                photo_caption,
                image_id=ho_photo_id
                )

        elif new_text:
            logger.info(
                '[TELESYNC] forwarding photo caption from TG: %s to HO: %s',
                msg.chat_id,
                ho_conv_id
                )
            self.sending += 1
            yield from bot.coro_send_message(ho_conv_id, photo_caption)

    @asyncio.coroutine
    def _on_sticker(self, msg):
        """forward sticker as png

        use cached upload id if present

        Args:
            msg: Message instance
        """
        if not self.config['enable_sticker_sync']:
            return
        bot = self.ho_bot
        if bot.memory.exists(['telesync', 'tg2ho', msg.chat_id]):
            ho_conv_id = bot.memory.get_by_path(
                ['telesync', 'tg2ho', msg.chat_id]
                )

            text = msg.get_sync_text(ho_conv_id)
        elif bot.memory.exists(['telesync', 'channel2ho', msg.chat_id]):
            ho_conv_id = bot.memory.get_by_path(
                ['telesync', 'channel2ho', msg.chat_id]
                )
            text = ''
        else:
            # no sync target set for this chat
            return

        file_id = msg['sticker']['file_id']
        ho_photo_id = yield from self._get_ho_photo_id(file_id, 'sticker')

        logger.info(
            '[TELESYNC] forwarding sticker from TG: %s to HO: %s',
            msg.chat_id,
            ho_conv_id
            )
        self.sending += 1
        yield from bot.coro_send_message(
            ho_conv_id,
            text,
            image_id=ho_photo_id
            )

    @asyncio.coroutine
    def _on_membership_change(self, msg, action_map):
        """notify the connected hangout about a membership change

        can be muted via config entry, groupnames can be hidden as well

        action_map = {
            'config': -> key in config.json,
            'chataction': -> key of userdata in the message dict,
            'output': -> text-output
        }

        Args:
            msg: Message instance
            action_map: dict

        Returns:
            boolean, True if the tg chat is synced, otherwise False
        """
        bot = self.ho_bot
        if not bot.memory.exists(['telesync', 'tg2ho', msg.chat_id]):
            # no sync target set for this chat
            return False
        ho_conv_id = bot.memory.get_by_path(['telesync', 'tg2ho', msg.chat_id])
        sync_title = bot.get_config_suboption(ho_conv_id, 'sync_chat_titles')
        template = bot.get_config_suboption(
            ho_conv_id,
            'sync_format_member_change'
            )
        text = template.format(
            name=User(msg, chat_action=action_map['chataction']).name,
            text=action_map['output'],
            title=msg.get_group_name(
                show=sync_title
                )
            )
        logger.info(
            '[TELESYNC] %s%s',
            text,
            '' if sync_title else msg.get_group_name(show=True)
            )
        if bot.get_config_suboption(ho_conv_id, action_map['config']):
            self.sending += 1
            yield from bot.coro_send_message(ho_conv_id, text)
        return True

    @asyncio.coroutine
    def _on_user_join(self, msg):
        """notify the hangout about new member if set in config

        Args:
            msg: Message instance
        """
        action_map = {
            'config': 'sync_join_messages',
            'chataction': 'new_chat_member',
            'output': _('joined')
        }
        yield from self._on_membership_change(msg, action_map)

    @asyncio.coroutine
    def _on_user_leave(self, msg):
        """notify the hangout about left member if set in config

        Args:
            msg: Message instance
        """
        bot = self.ho_bot
        action_map = {
            'config': 'sync_leave_messages',
            'chataction': 'left_chat_member',
            'output': _('left')
        }
        synced = yield from self._on_membership_change(msg, action_map)

        # if chat is synced: remove the user chat id from chat data in memory
        if synced and bot.memory.exists(
                ['telesync', 'tg_data', msg.chat_id, 'user', msg.user.usr_id]
            ):
            bot.memory.pop_by_path(
                ['telesync', 'tg_data', msg.chat_id, 'user', msg.user.usr_id]
                )
            bot.memory.save()

    @asyncio.coroutine
    def _on_location_share(self, msg):
        """forward url with query for Google Maps

        Args:
            msg: Message instance
        """
        bot = self.ho_bot
        if not bot.memory.exists(['telesync', 'tg2ho', msg.chat_id]):
            return

        ho_conv_id = bot.memory.get_by_path(['telesync', 'tg2ho', msg.chat_id])
        text = msg.get_sync_text(ho_conv_id)
        logger.info(
            '[TELESYNC] forwarding location from TG: %s to HO: %s',
            msg.chat_id,
            ho_conv_id
            )
        self.sending += 1
        yield from bot.coro_send_message(ho_conv_id, text)

    @asyncio.coroutine
    def _on_supergroup_upgrade(self, msg):
        """migrate all data from old to new chat_id

        Args:
            msg: Message instance
        """
        bot = self.ho_bot

        if not bot.memory.exists(['telesync', 'tg2ho', msg.chat_id]):
            return

        old_chat_id = msg.chat_id
        new_chat_id = str(msg['migrate_to_chat_id'])
        ho_conv_id = bot.memory.pop_by_path(['telesync', 'tg2ho', old_chat_id])
        bot.memory.set_by_path(['telesync', 'ho2tg', ho_conv_id], new_chat_id)
        bot.memory.set_by_path(['telesync', 'tg2ho', new_chat_id], ho_conv_id)

        # transfer tg_chat data or init new data
        bot.memory.set_by_path(
            ['telesync', 'tg_data', new_chat_id],
            bot.memory.get_by_path(
                ['telesync', 'tg_data', new_chat_id]
                ).pop(old_chat_id, {'user': {}})
            )
        self.received.text[new_chat_id] = self.received.text.pop(
            old_chat_id,
            {}
            )
        self.received.photos[new_chat_id] = self.received.photos.pop(
            old_chat_id,
            {}
            )
        bot.memory.save()

        logger.info(
            '[TELESYNC] group %s upgraded to Supergroup %s',
            old_chat_id,
            new_chat_id
            )

    @asyncio.coroutine
    def _ensure_admin(self, tg_chat_id, msg):
        """return weather the user is admin, and respond if be_quiet is off

        Args:
            tg_chat_id: int
            msg: Message instance

        Returns:
            boolean, True if user is Admin, otherwise False
        """
        if not msg.user.user_id in self.config['admins']:
            if not self.config['be_quiet']:
                yield from self.sendMessage(
                    tg_chat_id,
                    _('This command is admin-only!')
                    )
            return False
        return True

    @asyncio.coroutine
    def _ensure_private(self, tg_chat_id, msg):
        """return weather the chat is private, and respond if be_quiet is off

        Args:
            tg_chat_id: int
            msg: Message instance

        Returns:
            boolean, True if chat is of type private, otherwise False
        """
        if msg.chat_type != 'private':
            if not self.config['be_quiet']:
                yield from self.sendMessage(
                    tg_chat_id,
                    _(
                        'Issue again in a private chat:\n'
                        'Tap on my name then hit the message icon'
                        )
                    )
            return False
        return True

    @asyncio.coroutine
    def _ensure_params(self, tg_chat_id, params, numbers=(1)):
        """check the number of params, and respond if be_quiet is off

        Args:
            tg_chat_id: int
            params: list of strings
            numbers: tuple, that contains the allowed numbers for elements

        Returns:
            boolean, True if the number is correct, otherwise False
        """
        if len(params) not in numbers:
            if not self.config['be_quiet']:
                if len(numbers) == 1 and numbers[0] == 0:
                    required = _('There should be no supplied')
                else:
                    required = _('Exactly {} are required').format(
                        ' or '.join(numbers)
                        )
                yield from self.sendMessage(
                    tg_chat_id,
                    _(
                        'Check arguments. {required}'.format(
                            required=required
                            )
                        ).strip()
                    )
            return False
        return True

    @asyncio.coroutine
    def _command_whoami(self, tg_chat_id, args):
        """answer with user_id of request message, private only

        /whereami

        Args:
            tg_chat_id: int
            args: dict
        """
        msg = args['msg']
        if self._ensure_private(tg_chat_id, msg):
            yield from self.sendMessage(
                tg_chat_id,
                _("Your Telegram user id is '{}'").format(msg.user.usr_id)
                )

    @asyncio.coroutine
    def _command_whereami(self, tg_chat_id, args):
        """answer with current tg_chat_id, admin only

        /whereami

        Args:
            tg_chat_id: int
            args: dict
        """
        msg = args['msg']
        if self._ensure_admin(tg_chat_id, msg):
            yield from self.sendMessage(
                tg_chat_id,
                _("This chat has the id '{}'").format(tg_chat_id)
                )

    @asyncio.coroutine
    def _command_set_sync_ho(self, tg_chat_id, args):
        """set sync with given hoid if not already set

        /setsyncho <hangout conv_id>

        Args:
            tg_chat_id: int
            args: dict
        """
        bot = self.ho_bot
        msg = args['msg']
        if not self._ensure_admin(tg_chat_id, msg):
            return

        params = args['params']
        if not self._ensure_params(tg_chat_id, params):
            return

        target = str(params[0])
        if bot.memory.exists(['telesync', 'tg2ho', str(tg_chat_id)]):
            current_target = bot.memory.get_by_path(
                ['telesync', 'tg2ho', str(tg_chat_id)]
                )
            if target == current_target:
                yield from self.sendMessage(
                    tg_chat_id,
                    "Sync target '{}' already set".format(target)
                    )
                return

            bot.memory.pop_by_path(['telesync', 'ho2tg', current_target])
            text = "Sync target updated to '{}'".format(target)
        else:
            text = "Sync target set to '{}'".format(target)

        bot.memory.set_by_path(['telesync', 'ho2tg', target], str(tg_chat_id))
        bot.memory.set_by_path(['telesync', 'tg2ho', str(tg_chat_id)], target)
        bot.memory.save()

        yield from self.sendMessage(tg_chat_id, text)

    @asyncio.coroutine
    def _command_clear_sync_ho(self, tg_chat_id, args):
        """unset sync for current chat

        /clearsyncho

        Args:
            tg_chat_id: int
            args: dict
        """
        bot = self.ho_bot
        msg = args['msg']
        # let non-admin user disable their own tg<->pHO sync
        if not (
                self._ensure_admin(tg_chat_id, msg) or \
                self._ensure_private(tg_chat_id, msg)
            ):
            return
        if bot.memory.exists(['telesync', 'tg2ho', str(tg_chat_id)]):
            ho_conv_id = bot.memory.pop_by_path(
                ['telesync', 'tg2ho', str(tg_chat_id)]
                )
            bot.memory.pop_by_path(['telesync', 'ho2tg', ho_conv_id])
            bot.memory.save()
            text = _('Sync target cleared')
        else:
            text = _('No target found for this chat')

        yield from self.sendMessage(tg_chat_id, text)

    @asyncio.coroutine
    def _command_add_admin(self, tg_chat_id, args):
        """add admin id to admin list if not present

        /addadmin <tg_user_id>

        Args:
            tg_chat_id: int
            args: dict
        """
        bot = self.ho_bot

        msg = args['msg']
        if not (
                self._ensure_admin(tg_chat_id, msg) and \
                self._ensure_private(tg_chat_id, msg)
            ):
            return

        params = args['params']
        if not self._ensure_params(tg_chat_id, params):
            return

        if str(params[0]) not in self.admins:
            self.admins.append(str(params[0]))
            bot.config.force_taint()
            bot.config.save()
            text = _('User added to admins')
        else:
            text = _('User is already an admin')

        yield from self.sendMessage(tg_chat_id, text)

    @asyncio.coroutine
    def _command_remove_admin(self, tg_chat_id, args):
        """pop admin id if present in admin list

        /removeadmin <tg_user_id>

        Args:
            tg_chat_id: int
            args: dict
        """
        bot = self.ho_bot

        msg = args['msg']
        if not (
                self._ensure_admin(tg_chat_id, msg) and \
                self._ensure_private(tg_chat_id, msg)
            ):
            return

        params = args['params']
        if not self._ensure_params(tg_chat_id, params):
            return

        target_user = str(params[0])

        if target_user in self.config['admins']:
            self.config['admins'].remove(target_user)
            bot.config.force_taint()
            bot.config.save()
            text = _('User removed from admins')
        else:
            text = _('User is not an admin')

        yield from self.sendMessage(tg_chat_id, text)

    @asyncio.coroutine
    def _command_tldr(self, tg_chat_id, args):
        """get tldr for connected conv

        /tldr

        Args:
            tg_chat_id: int
            args: dict
        """
        bot = self.ho_bot
        if not bot.memory.exists(['telesync', 'tg2ho', str(tg_chat_id)]):
            return
        ho_conv_id = bot.memory.get_by_path(
            ['telesync', 'tg2ho', str(tg_chat_id)]
            )
        text = '{botcmd} tldr {args}'.format(
            botcmd=bot.memory['bot.command_aliases'][0],
            args=' '.join(args['params'])
            ).strip()
        fake_event = hangups_event.FakeEvent(
            bot=bot,
            conv_id=ho_conv_id,
            user_id=bot.user_self()['chat_id'],
            text=text
            )
        asyncio.ensure_future(bot._handlers.handle_command(fake_event))

    @asyncio.coroutine
    def _profilesync_info(self, tg_chat_id, is_reminder=False):
        """send info about pending profilesync to user

        Args:
            tg_chat_id: int
            is_reminder: bool
        """
        if is_reminder:
            html = _('<b> [ REMINDER ] </b>\n')
        else:
            html = ''
        bot_cmd = self.ho_bot.memory['bot.command_aliases'][0]
        html += _(
            '<b>Please send me the message bellow in our private Hangout:</b>\n'
            'Note: The message must start with <b>{bot_cmd}</b>, otherwise I do'
            'not process your message as a command and ignore your message.\n'
            'If you copy the message below, Telegram might add <b>{name}:</b> '
            'to my message. Just delete that until the message starts with <b>'
            '{bot_cmd}</b>.\n'
            'Our private Hangout and this chat will be automatcally synced. You'
            'can then receive mentions and other text that I only send to '
            'private Hangouts. Use <i>split</i>  next to the token to block '
            'this sync.\n'
            'Use /unsyncprofile to cancel the process.'
            ).format(bot_cmd=bot_cmd, name=self.user.name)
        token = self.ho_bot.memory.get_by_path(
            ['telesync', 'profilesync', 'pending_tg', str(tg_chat_id)]
            )
        yield from self.send_html(tg_chat_id, html)
        yield from self.sendMessage(
            tg_chat_id,
            '{} syncprofile {}'.format(bot_cmd, token)
            )
        yield from self.send_html(
            tg_chat_id,
            '{} syncprofile {} <i>split</i>'.format(bot_cmd, token)
            )

    @asyncio.coroutine
    def _command_sync_profile(self, tg_chat_id, args):
        """init profilesync, needs confirmation via pHO

        /syncprofile

        Args:
            tg_chat_id: int
            args: dict
        """
        bot = self.ho_bot
        msg = args['msg']
        if not self._ensure_private(tg_chat_id, msg):
            return

        if bot.memory.exists(
                ['telesync', 'profilesync', 'tg2ho', msg.user.usr_id]
            ):
            text = _(
                'Your profile is already linked to a G+Profile, use '
                '/unsyncprofile to unlink your profiles'
                )
            yield from self.sendMessage(tg_chat_id, text)
            return
        elif bot.memory.exists(
                ['telesync', 'profilesync', 'pending_tg', msg.user.usr_id]
            ):
            yield from self._profilesync_info(
                msg.user.usr_id,
                is_reminder=True
                )
            return

        token = None
        # get unique token
        while not token or bot.memory.exists(
                ['telesync', 'profilesync', 'pending_ho', token]
            ):
            token = ''.join(
                random.SystemRandom().sample(
                    TOKEN_CHAR,
                    5
                    )
                )

        bot.memory.set_by_path(
            ['telesync', 'profilesync', 'pending_tg', msg.user.usr_id],
            token
            )
        bot.memory.set_by_path(
            ['telesync', 'profilesync', 'pending_ho', token],
            (msg.user.usr_id, str(tg_chat_id))
            )
        bot.memory.save()

        yield from self._profilesync_info(tg_chat_id)

    @asyncio.coroutine
    def _command_unsync_profile(self, tg_chat_id, args):
        """split tg and ho-profile

        /unsyncprofile

        Args:
            tg_chat_id: int
            args: dict
        """
        bot = self.ho_bot
        msg = args['msg']
        if not self._ensure_private(tg_chat_id, msg):
            return

        user_id = msg.user.usr_id
        if bot.memory.exists(['telesync', 'profilesync', 'tg2ho', user_id]):
            ho_user_id = bot.memory.pop_by_path(
                ['telesync', 'profilesync', 'tg2ho', user_id]
                )
            bot.memory.pop_by_path(
                ['telesync', 'profilesync', 'ho2tg', ho_user_id]
                )
            if bot.memory.exists(['telesync', 'tg2ho', user_id]):
                ho_conv_id = bot.memory.pop_by_path(
                    ['telesync', 'tg2ho', user_id]
                    )
                bot.memory.pop_by_path(['telesync', 'ho2tg', ho_conv_id])
            bot.memory.save()
            text = _('Telegram and G+Profile are no more linked.')

        elif bot.memory.exists(
                ['telesync', 'profilesync', 'pending_tg', user_id]
            ):
            token = bot.memory.pop_by_path(
                ['telesync', 'profilesync', 'pending_tg', user_id]
                )
            bot.memory.pop_by_path(
                ['telesync', 'profilesync', 'pending_ho', token]
                )
            text = _('Profilesync canceled.')
        else:
            text = _(
                'There is no G+Profile connected to your Telegram Profile.\n'
                'Use /syncprofile to connect one'
                )

        yield from self.sendMessage(tg_chat_id, text)

    @asyncio.coroutine
    def _command_get_me(self, tg_chat_id, args):
        """send back info to bot user: id, name, username

        /getme

        Args:
            tg_chat_id: int
            args: dict
        """
        msg = args['msg']
        if not self._ensure_admin(tg_chat_id, msg):
            return

        yield from self.sendMessage(
            tg_chat_id,
            'id: {usr_id}, name: {name}, username: @{username}'.format(
                usr_id=self.user.usr_id,
                name=self.user.name,
                username=self.user.username
                )
            )

    @asyncio.coroutine
    def _command_echo(self, tg_chat_id, args):
        """send back params

        /echo {text}

        Args:
            tg_chat_id: int
            args: dict
        """
        msg = args['msg']
        if not self._ensure_admin(tg_chat_id, msg):
            return
        params = args['params']
        if not len(params):
            return
        yield from self.send_html(
            tg_chat_id,
            ' '.join(params),
            )

    @asyncio.coroutine
    def _command_get_admins(self, tg_chat_id, args):
        """send back a formated list of Admins

        /getadmins

        Args:
            tg_chat_id: int
            args: dict
        """
        msg = args['msg']
        if not self._ensure_private(tg_chat_id, msg):
            return
        admin_names = []
        bot = self.ho_bot
        for admin in self.config['admins']:
            if bot.memory.exists(
                    ['telesync', 'profilesync', 'usernames', admin]
                ):
                tg_name = bot.memory.get_by_path(
                    ['telesync', 'profilesync', 'usernames', admin]
                    )
            else:
                tg_name = '<i>{}</i>'.format(admin)
            if bot.memory.exists(
                    ['telesync', 'profilesync', 'tg2ho', admin]
                ):
                ho_id = bot.memory.get_by_path(
                    ['telesync', 'profilesync', 'tg2ho', admin]
                    )
                ho_name = bot.get_hangups_user(
                    ho_id
                    ).full_name
                user_link = (
                    "<a href='https://plus.google.com/{uid}'>{uname}</a>"
                    ).format(
                        uid=ho_id,
                        uname=ho_name
                        )
                admin_names.append('TG: {} | HO: {}'.format(tg_name, user_link))
            else:
                admin_names.append(tg_name)
        html = _('<b>Telegram Botadmins:</b>\n') + '\n'.join(admin_names)
        yield from self.send_html(tg_chat_id, html)

    @asyncio.coroutine
    def _command_leave(self, tg_chat_id, args):
        """leave the current chat

        /leave

        Args:
            tg_chat_id: int
            args: dict
        """
        msg = args['msg']
        if not self._ensure_admin(tg_chat_id, msg):
            return
        yield from self.sendMessage(tg_chat_id, _("I'll be back!"))
        try:
            has_left = yield from self.leaveChat(tg_chat_id)
            if has_left:
                return
        except telepot.exception.TelegramError:
            logger.exception('[TELESYNC] bot can not leave requsted chat')
        yield from self.sendMessage(
            tg_chat_id,
            'Sorry, but I am not able to leave this chat on my own.'
            )
