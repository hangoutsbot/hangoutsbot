"""Sync plugin for the Hangoutsbot with Telegram"""

import asyncio
import contextlib
import io
import logging
import os
import random
import urllib.request
import hangups
import hangups_event
import plugins
from .telegrambot import TelegramBot, util_html_bold

logger = logging.getLogger(__name__)

def _initialise(bot):
    """init bot for telesync, create and start a TelegramBot, register handler

    setup config and memory entrys, create TelegramBot and initialise it before
    starting the message loop, add commands to the hangupsbot and TelegramBot,
    start additional coros for TelegramBot, register handler for HO-messages

    Args:
        bot: hangupsbot instance
    """
    setup_config(bot)
    setup_memory(bot)

    try:
        # ensure that no message_loop is running
        if bot.tg_bot.loop_task and not bot.tg_bot.loop_task.cancelled():
            bot.tg_bot.loop_task.cancel()
            logger.info(
                'found running message_loop and stopped it: %s',
                bot.tg_bot.loop_task
                )
    except AttributeError:
        pass
    bot.tg_bot = None
    if not bot.config.get_by_path(['telesync', 'enabled']):
        return

    tg_bot = bot.tg_bot = TelegramBot(bot)
    tg_bot.loop_task = plugins.start_asyncio_task(tg_bot.start)

    plugins.start_asyncio_task(tg_bot.received.periodic_cleanup)
    plugins.start_asyncio_task(tg_bot.periodic_profilesync_reminder)
    plugins.register_handler(_on_hangouts_message, 'allmessages')
    plugins.register_handler(_on_membership_change, 'membership')
    plugins.register_user_command(['syncprofile'])
    plugins.register_admin_command(['tele_stop', 'telesync'])

def setup_config(bot):
    """register all attributes in config

    Args:
        bot: hangupsbot instance
    """
    default_config_telesync = {
        # telegram-admin ids
        'admins': [],

        # from botfather
        'api_key': 'PUT_YOUR_TELEGRAM_API_KEY_HERE',

        # no spam from commands if permissions/chat types do not match
        'be_quiet': True,

        # if True, the photos will be removed after Upload
        'do_not_keep_photos': True,

        'enable_sticker_sync': True,

        # enable the sync
        'enabled': True,

        # check new message in a channel against the last n messages
        'c_filter_received_n': 10,

        # custom path to store pictures after download/before upload
        'photo_path': '/tmp/telesync_photos_{botname}',

        # remind the user on the pending sync every n hours
        'profilesync_reminder': 36,

        # cleanup the sources for channel-filter and edit-track every n seconds
        'sleep_after_clean_up': 600,

        # resize sticker to max width and max height, in px
        'sticker_max_size': 256,

        # store source for channel-filter and edit-track in RAM or memory.json
        # second one keeps track over reboot, True for memory.json
        'store_messages': False,

        # store source for channel-filter and edit-track in RAM or memory.json
        # second one keeps track over reboot, True for memory.json
        'store_photoids': True,

        # sync the reply message, limit is set via reply_limit_{type}
        'sync_reply_to': True,

        # save last n messages to keep track of edits/new messages
        'track_edits': 20,

        # custom label to mark an updated Telegram message
        'update_label': 'Update'
    }

    default_config = {
        # use this also for other syncs and tg-replys can be formatted correct
        'global_sync_separator': ' : ',

        # set the next entrys global to be then able to set them also per conv
        #   as access is via bot.get_config_suboption
        'sync_chat_titles' : False,
        'sync_join_messages': True,
        'sync_leave_messages': True,

        # available keys: name, text, title, separator
        # activate 'sync_chat_titles' to use the title key
        'sync_format_member_change': '{name} {text} {title}',
        'sync_format_message': '{name} {title}{separator}{text}',

        # after n char cut and add '...', setting for all other chat_types
        'sync_reply_limit': 50,
        # after n char cut and add '...', setting for channels
        'sync_reply_limit_tg-channel': 30,
        'telesync': default_config_telesync
    }

    # validate config
    _validate_dict(bot, 'config', [], default_config)

    if not len(bot.config.get_by_path(['telesync', 'api_key'])):
        bot.config.set_by_path(['telesync', 'enabled'], False)
    if not len(bot.config.get_by_path(['global_sync_separator'])):
        bot.config.set_by_path(
            ['global_sync_separator'],
            default_config['global_sync_separator']
            )

    if bot.config.changed:
        bot.config.save()

def setup_memory(bot):
    """create all dicts in memory

    Args:
        bot: hangupsbot instance
    """
    default_memory = {
        # tg-channel -> ho
        'channel2ho': {},

        # ho -> tg
        'ho2tg': {},

        # sync tg- and g+ profiles to provide
        # propper names for syncs, bot-commands, mentions (opt)
        'profilesync': {
            # syncs, index g+id
            'ho2tg': {},

            # tg-usernames
            'usernames': {},

            # pending syncs, index g+id
            'pending_ho': {},

            # pending syncs, index tg-id
            'pending_tg': {},

            # syncs, index tg-id
            'tg2ho': {}
        },
        # set in config store_{messages, photoids}, to store the data here
        'received': {
            # photo-id to google-file-id
            'photo_ids': {},

            # sub dicts for each chat, photo-id to message id
            'photos': {},

            # sticker file id to google-file-id
            'sticker': {},

            # sub dicts for each chat, message id to text/photocaption
            'text': {}
        },
        # tg-chat {private, group, supergroup} -> ho
        'tg2ho': {},

        # sub dicts for each chat, store users in each chat
        'tg_data': {}
    }

    # validate memory
    _validate_dict(bot, 'memory', ['telesync'], default_memory)

    if bot.memory.changed:
        bot.memory.save()

def _validate_dict(bot, target, stack, source):
    """set the targets dict the stack points to, to the structure of the source

    check existance of each key in source, check type and entrys of the values

    Args:
        bot: hangups instance
        target: attribute of bot, such as 'config' or 'memory'
        stack: list of keys to the dict to validate
        source: default dict structure
    """
    for key, value in source.items():
        if not getattr(bot, target).exists(stack + [key]):
            getattr(bot, target).set_by_path(stack + [key], value)
        elif not isinstance(
                getattr(bot, target).get_by_path(stack + [key]),
                type(value)
            ):
            getattr(bot, target).set_by_path(stack + [key], value)
        elif isinstance(value, dict) and len(value):
            _validate_dict(bot, target, stack + [key], value)

@asyncio.coroutine
def _util_is_valid_image_link(url):
    """verify fileextension from link or from headers

    Args:
        url: string

    Returns:
        string: the valid file_name or an empty string
    """
    url = url.strip()
    if ' ' in url or not url.startswith(('http://', 'https://')):
        return ''
    valid_extensions = (
        '.jpg', '.jpeg', '.gif', '.gifv', '.webm', '.png', 'webp'
        )
    if url.endswith(valid_extensions):
        file_name = url.rpartition('/')[2]
        return file_name
    try:
        with contextlib.closing(urllib.request.urlopen(url)) as resp:
            file_name = resp.info().get_filename()
            if not file_name:
                file_name = ''
            if not file_name.endswith(valid_extensions):
                file_name = ''
    except urllib.error.HTTPError:
        file_name = ''
    return file_name

def _util_is_animated_photo(file_name):
    """return if extension is a known extension for animated files

    Args:
        file_name: string

    Returns:
        True if animated, otherwise False
    """
    return file_name.rpartition('.')[-1].endswith(
        ('.gif', '.gifv', '.webm', '.mp4')
        )

@asyncio.coroutine
def _util_get_event_content(bot, event):
    """check event for photos to download them, return the text and file objects

    Args:
        bot: hangupsbot
        event: hangups Event instance

    Returns:
        tuple of string and list:
            text without photo-links
            a list of tupel with info about downloads: path and file object
                the file object is
                    io.BytesIO, if config entry 'do_not_keep_photos' is True
                    open(path, 'rb'), otherwise
    """
    tg_bot = bot.tg_bot
    text_lines = []
    photos = set()
    for item in event.text.split('\n') + event.conv_event.attachments:
        file_name = yield from _util_is_valid_image_link(item)
        if len(file_name):
            photos.add((item.strip(), file_name))
        else:
            text_lines.append(item)

    text = '\n'.join(text_lines)

    downloaded_files = []
    for link, file_name in photos:
        # verify an existing location for downloading the photos
        if not os.path.exists(TelegramBot.PHOTO_PATH):
            if not tg_bot.update_photo_path():
                # no photo_path available, fallback to in memory handling
                tg_bot.config['do_not_keep_photos'] = True

        photo_path = (TelegramBot.PHOTO_PATH + '/{rand}-{file_name}').format(
            botname=tg_bot.user.name,
            rand=random.randint(1, 100000),
            file_name=file_name
            )

        with contextlib.closing(urllib.request.urlopen(link)) as resp:
            if tg_bot.config['do_not_keep_photos']:
                downloaded_files.append((photo_path, io.BytesIO(resp.read())))
            else:
                with open(photo_path, 'wb') as file:
                    file.write(resp.read())
                    downloaded_files.append(
                        (
                            photo_path,
                            open(photo_path, 'rb')
                            )
                        )
    return text, downloaded_files

def _util_format_sync_text(name, title, text, template, html=True):
    """format the sync message for the other chat

    Args:
        name: string, sender name - empty on bot message
        title: string, groupname - can be empty
        text: string, message for the chat
        template: string, use custom template for the message layout
        html: boolean, trigger the html bold tag for separator and title

    Returns:
        string, formated text for the chat
    """
    if title:
        title = '({})'.format(util_html_bold(title) if html else title)
    return template.format(
        name=name,
        title=title,
        separator=TelegramBot.SEPARATOR,
        text=text
        )

def _util_get_event_text(event, text, template='', name=''):
    """return stripped text,

    Args:
        event: hangups Event instance
        text: string, raw_text for the message
        template: string, use custom template for message layout
        name: string, predefined text, use to skip message parsing

    Returns:
        tupel of 2 strings, the first entry is the message without html tags,
            the second is with html tags
    """
    if event.user.is_self or len(name):
        if TelegramBot.SEPARATOR in event.text:
            # message from other sync
            name, text = text.partition(TelegramBot.SEPARATOR)[0:3:2]
        else:
            # bot message
            template = '{text}'
        name_html = util_html_bold(name)
    else:
        name = event.user.full_name
        gplus_url = 'https://plus.google.com/{uid}'.format(
            uid=event.user_id.chat_id
            )
        name_html = "<a href='{user_gplus}'>{uname}</a>".format(
            uname=name,
            user_gplus=gplus_url
            )
    title = ''
    if event.bot.get_config_suboption(event.conv_id, 'sync_chat_titles'):
        title = event.bot.conversations.get_name(event.conv)
    return (
        _util_format_sync_text(name, title, _('[Photo]'), template, html=False),
        _util_format_sync_text(name_html, title, text, template)
        )


@asyncio.coroutine
def tele_stop(bot, event, *args):
    """stop telesync loop or start it again in a serperate loop

    Note:
        this loop is detached from the plugin loader:
        once you restarted the sync with ! tele_stop again, simply unloading
        telesync via ! pluginunload will not stop the messageloop, use
        ! tele_stop again to stop the loop

    ! tele_stop

    Args:
        bot: hangupsbot instance
        event: hangups_event
        args: additional text as tupel
    """
    if event.user_id.chat_id not in bot.config['admins']:
        yield from bot.coro_send_message(
            event.conv_id,
            _('This comand is Admin-only.')
            )

    tg_bot = bot.tg_bot
    if tg_bot.loop_task and not tg_bot.loop_task.cancelled():
        tg_bot.loop_task.cancel()
        html = _('[GLOBAL] sync changed to one-way<br />HO -> TG')
    elif tg_bot.loop_task and tg_bot.loop_task.cancelled():
        loop = asyncio.get_event_loop()
        tg_bot.loop_task = loop.create_task(tg_bot.message_loop())
        html = _('[GLOBAL] two-way sync resumed <br />HO <-> TG')
    else:
        html = _('sync is disabled')
    yield from bot.coro_send_message(event.conv_id, html)

@asyncio.coroutine
def syncprofile(bot, event, *args):
    """syncs ho-user with tg-user-profile and syncs pHO <-> tg-pm

    ! syncprofile <token>
    ! syncprofile <token> split
    token is generated on tg-side

    Args:
        bot: hangupsbot instance
        event: hangups_event
        args: additional text as tupel
    """
    bot_cmd = bot.memory['bot.command_aliases'][0]
    if len(args) == 0 or (len(args) > 1 and args[1].lower() != 'split'):
        help_html = _(
            '<b>Usage:</b><br />'
            '{bot_cmd} syncprofile <token><br />'
            '{bot_cmd} syncprofile <token> split<br />'
            'The addition <i>split</i>  sets no sync between private Hangout '
            'and private Telegram Chat.<br />'
            'Example:<br />'
            '{bot_cmd} syncprofile DEMO123 <br />'
            '{bot_cmd} syncprofile 123DEMO split'
            ).format(bot_cmd=bot_cmd)
        yield from bot.coro_send_message(event.conv_id, help_html)
        return

    conv_1on1 = yield from bot.get_1to1(event.user.id_.chat_id)
    if not conv_1on1:
        html = _('Disable DND first:')
        yield from bot.coro_send_message(event.conv_id, html)
        html = '{} optin'.format(bot_cmd)
        yield from bot.coro_send_message(event.conv_id, html)
        return
    conv_1on1 = conv_1on1.id_

    ho_user_id = str(event.user_id.chat_id)
    if bot.memory.exists(['telesync', 'profilesync', 'ho2tg', ho_user_id]):
        html = _(
            'I found a connection between this G+Profile and the Telegram '
            'Profile {}. Send me /unsyncprofile our private Telegram chat to '
            'disconnect them.'
            )
        yield from bot.coro_send_message(conv_1on1, html)
        return
    elif not bot.memory.exists(
            ['telesync', 'profilesync', 'pending_ho', args[0]]
        ):
        html = _(
            'Check your spelling or start the sync via Telegram <i>again</i>\n'
            'Open a private chat with {bot_username} '
            'https://t.me/{bot_username} and send me'
            ).format(bot_username=bot.tg_bot.user.username)
        yield from bot.coro_send_message(conv_1on1, html)
        yield from bot.coro_send_message(conv_1on1, '/syncprofile')
        return

    tg_id, tg_chat = bot.memory.get_by_path(
        ['telesync', 'profilesync', 'pending_ho', args[0]]
        )

    # profile sync
    bot.memory.set_by_path(
        ['telesync', 'profilesync', 'tg2ho', tg_id],
        ho_user_id
        )
    bot.memory.set_by_path(
        ['telesync', 'profilesync', 'ho2tg', ho_user_id],
        tg_id
        )
    text = _('Your profiles are now connected')

    # chat sync
    if len(args) == 1:
        bot.memory.set_by_path(['telesync', 'tg2ho', tg_chat], conv_1on1)
        bot.memory.set_by_path(['telesync', 'ho2tg', conv_1on1], tg_chat)
        text = _(
            'Your profiles are now connected and you will receive my messages'
            ' in Telegram as well.'
            )

    # cleanup
    bot.memory.pop_by_path(
        ['telesync', 'profilesync', 'pending_ho', args[0]]
        )
    bot.memory.pop_by_path(
        ['telesync', 'profilesync', 'pending_tg', tg_id]
        )
    bot.memory.save()

    yield from bot.coro_send_message(conv_1on1, text)

@asyncio.coroutine
def telesync(bot, event, *args):
    """set a telegram chat as sync target for the current ho

    /bot telesync <telegram chat id> - set sync with telegram group
    /bot telesync - disable sync and clear sync data from memory

    Args:
        bot: hangupsbot instance
        event: hangups_event
        args: additional text as tupel
    """
    if len(args) > 1:
        yield from bot.coro_send_message(
            event.conv_id,
            _('Too many arguments')
            )

    elif len(args) == 0:
        if bot.memory.exists(['telesync', 'ho2tg', str(event.conv_id)]):
            tg_chat_id = bot.memory.pop_by_path(
                ['telesync', 'ho2tg', str(event.conv_id)]
                )
            bot.memory.pop_by_path(['telesync', 'tg2ho', str(tg_chat_id)])
            bot.memory.save()

        yield from bot.coro_send_message(
            event.conv_id,
            _('Sync target cleared')
            )

    else:
        tg_chat_id = str(args[0])
        if bot.memory.exists(['telesync', 'ho2tg', str(event.conv_id)]):
            current_target = bot.memory.get_by_path(
                ['telesync', 'tg2ho', str(tg_chat_id)]
                )
            if tg_chat_id == current_target:
                yield from bot.coro_send_message(
                    event.conv_id,
                    _("Sync target '{}' already set").format(tg_chat_id)
                    )
                return
            bot.memory.pop_by_path(['telesync', 'tg2ho', current_target])
            text = _("Sync target updated to '{}'").format(tg_chat_id)
        else:
            text = _("Sync target set to '{}'").format(tg_chat_id)
            bot.memory.set_by_path(
                ['telesync', 'ho2tg', str(event.conv_id)],
                tg_chat_id
                )
            bot.memory.set_by_path(
                ['telesync', 'tg2ho', tg_chat_id],
                str(event.conv_id)
                )
            bot.memory.save()
            yield from bot.coro_send_message(
                event.conv_id,
                text
                )

@asyncio.coroutine
def _on_hangouts_message(bot, event, command):
    """forward message/photos from all users via Hangouts to Telegram

    Args:
        bot: hangupsbot instance
        event: hangups_event
        command: command handle from commands
    """
    tg_bot = bot.tg_bot
    if not bot.memory.exists(['telesync', 'ho2tg', event.conv_id]):
        return
    if event.user.is_self and tg_bot.sending and (
            (TelegramBot.SEPARATOR in event.text) or \
                any(item in event.text for item in (_('joined'), _('left')))
        ):
        # this is a synced message
        tg_bot.sending -= 1
        return
    tg_chat_id = bot.memory.get_by_path(['telesync', 'ho2tg', event.conv_id])

    text, downloaded_files = yield from _util_get_event_content(bot, event)

    logger.info(
        '[TELESYNC] Forwarding %s%s%s from HO: %s to TG: %s',
        'Text' if len(text) else '',
        ' and ' if len(text) and len(downloaded_files) else '',
        'Media' if len(downloaded_files) else '',
        event.conv_id,
        tg_chat_id
        )

    # TG-Photo-Captions are not allowed to contain html, caption handled extra
    text_photo, text_html = _util_get_event_text(
        event,
        text,
        template=bot.get_config_suboption(event.conv_id, 'sync_format_message')
        )

    if len(downloaded_files) == 1:
        photo_info = downloaded_files[0]
        if _util_is_animated_photo(photo_info[0]):
            yield from tg_bot.sendDocument(
                tg_chat_id,
                photo_info[1]
                )
        else:
            yield from tg_bot.sendPhoto(
                tg_chat_id,
                photo_info[1],
                caption=text_photo,
                )
            photo_info[1].close()
    else:
        for photo_info in downloaded_files:
            if _util_is_animated_photo(photo_info[0]):
                yield from tg_bot.sendDocument(
                    tg_chat_id,
                    photo_info[1]
                    )
            else:
                yield from tg_bot.sendPhoto(
                    tg_chat_id,
                    photo_info[1],
                    caption=text_photo
                    )
                photo_info[1].close()
    if len(text):
        yield from tg_bot.send_html(
            tg_chat_id,
            text_html
            )

@asyncio.coroutine
def _on_membership_change(bot, event, command):
    """notify a configured tg-chat about a membership change

    Args:
        bot: hangupsbot instance
        event: hangups_event
        command: command handle from commands
    """
    if not bot.memory.exists(['telesync', 'ho2tg', event.conv_id]):
        return

    if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        text = _('joined')
        config_entry = 'sync_join_messages'
    else:
        text = _('left')
        config_entry = 'sync_leave_messages'

    if not bot.get_config_suboption(event.conv_id, config_entry):
        return

    if len(event.conv_event.participant_ids) > 1:
        # Generate list of added or removed users
        event_users_names = [
            event.conv.get_user(
                user_id
                ).full_name for user_id in event.conv_event.participant_ids
            ]
        names = util_html_bold(', '.join(event_users_names))
        fake_event = event
    else:
        names = ''
        fake_event = hangups_event.FakeEvent(
            bot=bot,
            conv_id=event.conv_id,
            user_id=event.conv.get_user(
                event.conv_event.participant_ids[0]
                ).id_.chat_id,
            text=text
            )

    template = bot.get_config_suboption(
        event.conv_id,
        'sync_format_member_change'
        )

    text = _util_get_event_text(
        fake_event,
        text,
        template,
        name=names
        )[1]

    yield from bot.tg_bot.send_html(
        bot.memory.get_by_path(['telesync', 'ho2tg', event.conv_id]),
        text
        )
