import os
import hangups

from hangups.ui.utils import get_conv_name

class logger():
    _bot = None
    _config = None

    _log_path = ""

    def _append_to_file(conversation_id, text):
        conversation_log = logger._log_path + "/" + conversation_id + ".txt"
        with open(conversation_log, "a") as logfile:
            logfile.write(text)

    def init():
        if "storage_path" in logger._config:
            if logger._config["storage_path"]:
                path = logger._config["storage_path"]

                # create the directory if it does not exist
                directory = os.path.dirname(path)
                if directory and not os.path.isdir(directory):
                    try:
                        os.makedirs(directory)
                    except OSError as e:
                        print('logger failed to create directory: {}'.format(e))
                        return False

                logger._log_path = directory
                print("logger will store chats in {}".format(logger._log_path))
            else:
                print("logger failed to initialise: config.hooks[].storage_path cannot be empty")
                return False

        else:
            print("logger failed to initialise: config.hooks[].storage_path not provided")
            return False

        return True

    def on_chat_message(event):
        event_timestamp = event.timestamp

        conversation_id = event.conv_id
        conversation_name = get_conv_name(event.conv)
        conversation_text = event.text

        user_full_name = event.user.full_name
        user_id = event.user_id

        text = "--- {}\n{} :: {}\n{}\n".format(conversation_name, event_timestamp, user_full_name, conversation_text)

        logger._append_to_file(conversation_id, text)

    def on_membership_change(event):
        event_timestamp = event.timestamp

        conversation_id = event.conv_id
        conversation_name = get_conv_name(event.conv)
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

        logger._append_to_file(conversation_id, text)

    def on_rename(event):
        event_timestamp = event.timestamp

        conversation_id = event.conv_id
        conversation_name = get_conv_name(event.conv)
        conversation_text = event.text

        user_full_name = event.user.full_name
        user_id = event.user_id

        text = "--- {}\n{} :: {}\nCONVERSATION RENAMED: {}\n".format(conversation_name, event_timestamp, user_full_name, conversation_name)

        logger._append_to_file(conversation_id, text)