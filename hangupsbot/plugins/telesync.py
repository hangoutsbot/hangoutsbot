# A Sync plugin for Telegram and Hangouts

import os, logging
import asyncio
import hangups
import plugins
import telepot

# TEST VARIABLES
TG_BOT_TOKEN = "TELEGRAM_BOT_API_KEY_FROM_BOTFATHER"
TG_TARGET_CHAT_ID = 999999999

logger = logging.getLogger(__name__)

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
        print("[HANDLE]")
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
                    self.sendMessage(chat_id, "[TXT] {msg}".format(msg=msg_text))

        elif flavor == "inline_query":  # inline query e.g. "@gif cute panda"
            query_id, from_id, query_string = telepot.glance2(msg, flavor=flavor)
            print("inline_query")

        elif flavor == "chosen_inline_result":
            result_id, from_id, query_string = telepot.glance2(msg, flavor=flavor)
            print("chosen_inline_result")

        else:
            raise telepot.BadFlavor(msg)


def tg_sample_on_message(bot, chat_id, msg):
    bot.sendMessage(chat_id, "msg received: {txt}".foramt(msg['text']))


# TELEGRAM DEFINITIONS END

# HANGOUTSBOT

tg_bot = 0


def _initialise(bot):
    global tg_bot
    tg_bot = TelegramBot(TG_BOT_TOKEN) # TODO: get telegram bot api key in a proper way
    tg_bot.set_on_message_callback(tg_sample_on_message)

    plugins.register_handler(_on_hangouts_message, type="message", priority=50)


def _on_hangouts_message(bot, event, command):
    tg_chat_id = TG_TARGET_CHAT_ID  # TODO: get proper telegram chat id
    tg_bot.sendMessage(tg_chat_id,  event.text)
