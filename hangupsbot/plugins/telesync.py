# A Sync plugin for Telegram and Hangouts

import os, logging
import asyncio
import hangups
import plugins
import telepot
from handlers import handler
from commands import command

logger = logging.getLogger(__name__)
ho_bot = 0


# TELEGRAM BOT


class TelegramBot(telepot.Bot):
    def __init__(self, token):
        super(TelegramBot, self).__init__(token)
        self.commands = {}
        self.onMessageCallback = TelegramBot.on_message

    def add_command(self, cmd, func):
        self.commands[cmd] = func

    def remove_command(self, cmd):
        if cmd in self.commands:
            del self.commands[cmd]

    @staticmethod
    def parse_command(cmd):
        txt_split = cmd.split()
        return txt_split[0], txt_split[1:]

    @staticmethod
    def on_message(bot, chat_id, msg):
        print("[MSG] {uid} : {txt}".format(uid=msg['from']['id'], txt=msg['text']))

    def set_on_message_callback(self, func):
        self.onMessageCallback = func

    def handle(self, msg):
        flavor = telepot.flavor(msg)

        if flavor == "normal":  # normal message
            content_type, chat_type, chat_id = telepot.glance2(msg)
            if content_type == "text":
                msg_text = msg['text']

                self.onMessageCallback(self, chat_id, msg)

                if msg_text[0] == "/":  # bot command
                    cmd, params = TelegramBot.parse_command(msg_text)
                    try:
                        self.commands[cmd](self, chat_id, params)
                    except KeyError:
                        self.sendMessage(chat_id, "Unknown command: {cmd}".format(cmd=cmd))

                else:  # plain text message
                    # self.sendMessage(chat_id, "[TXT] {msg}".format(msg=msg_text))
                    pass

        elif flavor == "inline_query":  # inline query e.g. "@gif cute panda"
            query_id, from_id, query_string = telepot.glance2(msg, flavor=flavor)
            print("inline_query")

        elif flavor == "chosen_inline_result":
            result_id, from_id, query_string = telepot.glance2(msg, flavor=flavor)
            print("chosen_inline_result")

        else:
            raise telepot.BadFlavor(msg)


def tg_on_message(tg_bot, tg_chat_id, msg):
    global ho_bot

    tg2ho_dict = ho_bot.memory.get_by_path(['telesync_tg2ho'])

    if tg_chat_id in tg2ho_dict:
        logger.info("[TELESYNC] telegram message received: {msg}".format(msg=msg['text']))

        target_ho = tg2ho_dict[tg_chat_id]
        text_msg = "to: {ho_id} | message: {txt}".format(ho_id=target_ho, txt=msg['text'])
        tg_bot.sendMessage(tg_chat_id, text_msg)
        ho_bot.coro_send_message(tg2ho_dict[tg_chat_id], text_msg)

        logger.info("[TELESYNC] telegram message forwarded: {msg}".format(msg=msg['text']))


def tg_command_whereami(bot, chat_id, params):
    bot.sendMessage(chat_id, "current group's id: {chat_id}".format(chat_id=chat_id))


def tg_command_set_sync_ho(bot, chat_id, params):  # /setsyncho <hangout conv_id>

    if len(params) != 1:
        bot.sendMessage(chat_id, "Illegal or Missing arguments!!!")
        return

    tg2ho_dict = ho_bot.memory.get_by_path(['telesync_tg2ho'])
    ho2tg_dict = ho_bot.memory.get_by_path(['telesync_ho2tg'])

    tg2ho_dict[str(chat_id)] = str(params[0])
    ho2tg_dict[str(params[0])] = str(chat_id)

    ho_bot.memory.set_by_path(['telesync_tg2ho'], tg2ho_dict)
    ho_bot.memory.set_by_path(['telesync_ho2tg'], ho2tg_dict)


# TELEGRAM DEFINITIONS END

# HANGOUTSBOT

tg_bot = 0


def _initialise(bot):
    if not bot.config.exists(['telegram_bot_api_key']):
        bot.config.set_by_path(['telegram_bot_api_key'], "PUT_YOUR_TELEGRAM_API_KEY_HERE")

    if not bot.memory.exists(['telesync_ho2tg']):
        bot.memory.set_by_path(['telesync_ho2tg'], {})

    if not bot.memory.exists(['telesync_tg2ho']):
        bot.memory.set_by_path(['telesync_tg2ho'], {})

    global tg_bot
    global ho_bot
    ho_bot = bot

    tg_bot_token = bot.config.get_by_path(['telegram_bot_api_key'])

    tg_bot = TelegramBot(tg_bot_token)
    tg_bot.set_on_message_callback(tg_on_message)
    tg_bot.add_command("/whereami", tg_command_whereami)
    tg_bot.add_command("/setsyncho", tg_command_set_sync_ho)

    tg_bot.notifyOnMessage()

    # plugins.register_handler(_on_hangouts_message, type="message", priority=50)


@handler.register(priority=50, event=hangups.ChatMessageEvent)
def _on_hangouts_message(bot, event, command=""):
    global tg_bot
    ho2tg_dict = ho_bot.memory.get_by_path(['telesync_ho2tg'])

    if event.conv_id in ho2tg_dict:
        text = "{uname} on {gname}: {text}".format(uname=event.user.full_name, gname=event.conv.name, text=event.text)
        tg_bot.sendMessage(ho2tg_dict[event.conv_id], text)
