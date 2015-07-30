import os, logging

import hangups

import plugins


logger = logging.getLogger(__name__)


def _initialise(bot):
    fileWriter = file_writer(bot)

    if fileWriter.initialised:
        plugins.register_handler(fileWriter.on_membership_change, type="membership")
        plugins.register_handler(fileWriter.on_rename, type="rename")
        plugins.register_handler(fileWriter.on_chat_message, type="allmessages")


class file_writer():
    bot = None
    paths = []
    initialised = False

    def __init__(self, bot):
        self.bot = bot
        self.paths = []
        self.initialised = False

        legacy_hooks = bot.get_config_option('hooks')
        if legacy_hooks:
            for legacy_config in legacy_hooks:
                if legacy_config["module"] == "hooks.chatlogger.writer.logger":
                    logger.warning('[DEPRECATED] legacy hook configuration, update to config["chatlogger.path"]')
                    self.paths.append(legacy_config["config"]["storage_path"])

        chatlogger_path = bot.get_config_option('chatlogger.path')
        if chatlogger_path:
            self.paths.append(chatlogger_path)

        self.paths = list(set(self.paths))

        for path in self.paths:
            # create the directory if it does not exist
            directory = os.path.dirname(path)
            if directory and not os.path.isdir(directory):
                try:
                    os.makedirs(directory)
                except OSError as e:
                    logger.exception('cannot create path: {}'.format(path))
                    continue

            logger.info("stored in: {}".format(path))

        if len(self.paths) > 0:
            self.initialised = True


    def _append_to_file(self, conversation_id, text):
        for path in self.paths:
            conversation_log = path + "/" + conversation_id + ".txt"
            with open(conversation_log, "a") as logfile:
                logfile.write(text)


    def on_chat_message(self, bot, event, command):
        event_timestamp = event.timestamp

        conversation_id = event.conv_id
        conversation_name = bot.conversations.get_name(event.conv)
        conversation_text = event.text

        user_full_name = event.user.full_name
        user_id = event.user_id

        text = "--- {}\n{} :: {}\n{}\n".format(conversation_name, event_timestamp, user_full_name, conversation_text)

        self._append_to_file(conversation_id, text)


    def on_membership_change(self, bot, event, command):
        event_timestamp = event.timestamp

        conversation_id = event.conv_id
        conversation_name = bot.conversations.get_name(event.conv)
        conversation_text = event.text

        user_full_name = event.user.full_name
        user_id = event.user_id

        event_users = [event.conv.get_user(user_id) for user_id
                       in event.conv_event.participant_ids]
        names = ', '.join([user.full_name for user in event_users])

        if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
            text = "--- {}\n{} :: {}\nADDED: {}\n".format(conversation_name, event_timestamp, user_full_name, names)
        else:
            text = "--- {}\n{}\n{} left \n".format(conversation_name, event_timestamp, names)

        self._append_to_file(conversation_id, text)


    def on_rename(self, bot, event, command):
        event_timestamp = event.timestamp

        conversation_id = event.conv_id
        conversation_name = bot.conversations.get_name(event.conv)
        conversation_text = event.text

        user_full_name = event.user.full_name
        user_id = event.user_id

        text = "--- {}\n{} :: {}\nCONVERSATION RENAMED: {}\n".format(conversation_name, event_timestamp, user_full_name, conversation_name)

        self._append_to_file(conversation_id, text)
