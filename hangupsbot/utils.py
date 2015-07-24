import importlib, logging, unicodedata

import hangups

from parsers import simple_parse_to_segments, segment_to_html

from permamem import conversation_memory as conversation_memory, get_conv_name, get_all_conversations


logger = logging.getLogger(__name__)


def text_to_segments(text):
    """Create list of message segments from text"""
    # Replace two consecutive spaces with space and non-breakable space,
    # then split text to lines
    lines = text.replace('  ', ' \xa0').splitlines()
    if not lines:
        return []

    # Generate line segments
    segments = []
    for line in lines[:-1]:
        if line:
            segments.append(hangups.ChatMessageSegment(line))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    if lines[-1]:
        segments.append(hangups.ChatMessageSegment(lines[-1]))

    return segments


def remove_accents(text):
    """remove accents from unicode text, allows east asian languages through"""
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')


def unicode_to_ascii(text):
    """Transliterate unicode characters to ASCII"""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()


def class_from_name(module_name, class_name):
    """adapted from http://stackoverflow.com/a/13808375"""
    # load the module, will raise ImportError if module cannot be loaded
    m = importlib.import_module(module_name)
    # get the class, will raise AttributeError if class cannot be found
    c = getattr(m, class_name)
    return c


class tags:
    bot = None

    indices = {}

    def __init__(self, bot):
        self.bot = bot
        self.refresh_indices()

    def _load_from_memory(self, key, type):
        if self.bot.memory.exists([key]):
            for id, data in self.bot.memory[key].items():
                if "tags" in data:
                    for tag in data["tags"]:
                        self.add_to_index(type, tag, id)

    def refresh_indices(self):
        self.indices = { "user-tags": {}, "tag-users":{}, "conv-tags": {}, "tag-convs": {} }

        self._load_from_memory("user_data", "user")
        self._load_from_memory("conv_data", "conv")

        # XXX: custom iteration to retrieve per-conversation-user-overrides
        if self.bot.memory.exists(["conv_data"]):
            for conv_id in self.bot.memory["conv_data"]:
                if self.bot.memory.exists(["conv_data", conv_id, "tags-users"]):
                    for chat_id, tags in self.bot.memory["conv_data"][conv_id]["tags-users"].items():
                        for tag in tags:
                            self.add_to_index("user", tag, conv_id + "|" + chat_id)

        logging.info("tags: refreshed")

    def add_to_index(self, type, tag, id):
        tag_to_object = "tag-{}s".format(type)
        object_to_tag = "{}-tags".format(type)

        if tag not in self.indices[tag_to_object]:
            self.indices[tag_to_object][tag] = []
        if id not in self.indices[tag_to_object][tag]:
            self.indices[tag_to_object][tag].append(id)

        if id not in self.indices[object_to_tag]:
            self.indices[object_to_tag][id] = []
        if tag not in self.indices[object_to_tag][id]:
            self.indices[object_to_tag][id].append(tag)

    def remove_from_index(self, type, tag, id):
        tag_to_object = "tag-{}s".format(type)
        object_to_tag = "{}-tags".format(type)

        if tag in self.indices[tag_to_object]:
            if id in self.indices[tag_to_object][tag]:
                self.indices[tag_to_object][tag].remove(id)

        if id in self.indices[object_to_tag]:
            if tag in self.indices[object_to_tag][id]:
                self.indices[object_to_tag][id].remove(tag)

    def update(self, type, id, action, tag):
        updated = False
        tags = None

        if type == "conv":
            index_type = "conv"

            if id not in self.bot.conversations.catalog:
                raise ValueError("tags: conversation {} does not exist".format(id))

            tags = self.bot.conversation_memory_get(id, "tags")

        elif type == "user":
            index_type = "user"

            if not self.bot.memory.exists(["user_data", id]):
                raise ValueError("tags: user {} does not exist".format(id))

            tags = self.bot.user_memory_get(id, "tags")

        elif type == "convuser":
            index_type = "user"
            [conv_id, chat_id] = id.split("|", maxsplit=1)

            if not self.bot.memory.exists(["user_data", chat_id]):
                raise ValueError("tags: user {} does not exist".format(id))
            if conv_id not in self.bot.conversations.catalog:
                raise ValueError("tags: conversation {} does not exist".format(conv_id))

            tags_users = self.bot.conversation_memory_get(conv_id, "tags-users")
            if not tags_users:
                tags_users = {}
            if chat_id in tags_users:
                tags = tags_users[chat_id]

        else:
            raise ValueError("tags: unhandled read type {}".format(type))

        if not tags:
            tags = []

        if action == "set":
            if tag not in tags:
                tags.append(tag)
                self.add_to_index(index_type, tag, id)
                updated = True

        elif action == "remove":
            try:
                tags.remove(tag)
                self.remove_from_index(index_type, tag, id)
                updated = True
            except ValueError as e:
                # in case the value does not exist
                pass

        else:
            raise ValueError("tags: unrecognised action {}".format(action))

        if updated:
            if type == "conv":
                self.bot.conversation_memory_set(id, "tags", tags)

            elif type == "user":
                self.bot.user_memory_set(id, "tags", tags)

            elif type == "convuser":
                tags_users[chat_id] = tags
                self.bot.conversation_memory_set(conv_id, "tags-users", tags_users)

            else:
                raise ValueError("tags: unhandled update type {}".format(type))

            logging.info("tags: {}/{} action={} value={}".format(type, id, action, tag))
        else:
            logging.info("tags: {}/{} action={} value={} [NO CHANGE]".format(type, id, action, tag))

        return updated

    def add(self, type, id, tag):
        """add tag to (type=conv/user) id"""
        return self.update(type, id, "set", tag)

    def remove(self, type, id, tag):
        """remove tag from (type=conv/user) id"""
        return self.update(type, id, "remove", tag)

    def useractive(self, chat_id, conv_id="*"):
        """return active tags of user for current conv_id if supplied, globally if not"""
        if conv_id != "*":

            if not self.bot.memory.exists(["user_data", chat_id]):
                raise ValueError("tags: user {} does not exist".format(chat_id))
            if conv_id not in self.bot.conversations.catalog:
                raise ValueError("tags: conversation {} does not exist".format(conv_id))

            per_conversation_user_override_key = (conv_id + "|" + chat_id)
            if per_conversation_user_override_key in self.indices["user-tags"]:
                return self.indices["user-tags"][per_conversation_user_override_key]

        if chat_id in self.indices["user-tags"]:
            return self.indices["user-tags"][chat_id]

        return []

    def userlist(self, conv_id, tags=False):
        """return dict of participating chat_ids to tags, optionally filtered by tag/list of tags"""

        if isinstance(tags, str):
            tags = [tags]

        userlist = self.bot.conversations.catalog[conv_id]["users"]

        results = {}
        for user in userlist:
            chat_id = user[0][0]
            user_tags = self.useractive(chat_id, conv_id)
            if tags and not set(tags).issubset(set(user_tags)):
                continue
            results[chat_id] = user_tags
        return results
