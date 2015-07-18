import importlib, unicodedata, sys, logging, datetime

import hangups

from parsers import simple_parse_to_segments, segment_to_html

from hangups.ui.utils import get_conv_name as hangups_get_conv_name

bot = None


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


def get_conv_name(conv, truncate=False):
    logging.warning("DEPRECATED: use bot.conversations.get_name()")
    return bot.conversations.get_name(conv)


def get_all_conversations(filter=False):
    logging.warning("DEPRECATED: use bot.conversations.get()")
    return bot.conversations.get(filter)


class conversation_memory:
    bot = None
    catalog = {}

    def __init__(self, bot):
        self.bot = bot
        self.catalog = {}
        self.load_from_memory()
        self.load_from_hangups()
        self.save_to_memory()
        logging.info("conversation_memory(): {} loaded".format(len(self.catalog)))

        sys.modules[__name__].bot = bot # workaround for drop-ins

    def load_from_hangups(self):
        logging.info("conversation_memory(): loading from hangups")
        for conv in self.bot._conv_list.get_all():
            self.update(conv, source="init", automatic_save=False)
 
    def load_from_memory(self):
        if self.bot.memory.exists(['convmem']):
            convs = self.bot.memory.get_by_path(['convmem'])
            logging.info("conversation_memory(): loading from memory {}".format(len(convs)))
            for convid in convs:
                self.catalog[convid] = convs[convid]

                """devs: add new conversation memory sub-keys here"""

                if "users" not in self.catalog[convid]:
                    self.catalog[convid]["users"] = []

                if "type" not in self.catalog[convid]:
                    self.catalog[convid]["type"] = "unknown"

                if self.catalog[convid]["type"] == "unknown":
                    """intelligently guess the type"""
                    if len(self.catalog[convid]["users"]) > 1:
                        self.catalog[convid]["type"] = "GROUP"
                    else:
                        if self.bot.memory.exists(["user_data"]):
                            """inefficient search, but its one-off"""
                            for userid in self.bot.memory["user_data"]:
                                if self.bot.memory.exists(["user_data", userid, "1on1"]):
                                    if self.bot.memory["user_data"][userid]["1on1"] == convid:
                                        self.catalog[convid]["type"] = "ONE_TO_ONE"
                                        break

                if "history" not in self.catalog[convid]:
                    self.catalog[convid]["history"] = True

    def save_to_memory(self):
        self.bot.memory.set_by_path(['convmem'], self.catalog)
        self.bot.memory.save()

    def update(self, conv, source="unknown", automatic_save=True):
        conv_title = hangups_get_conv_name(conv)
        if conv.id_ not in self.catalog:
            self.catalog[conv.id_] = {}

        """base information"""
        self.catalog[conv.id_] = {
            "title": conv_title,
            "source": source,
            "users" : [], # uninitialised
            "updated": datetime.datetime.now().strftime("%Y%m%d%H%M%S")}

        """store the user list"""
        self.catalog[conv.id_]["users"] = [[[user.id_.chat_id, user.id_.gaia_id], user.full_name ] for user in conv.users if not user.is_self]

        """store the conversation type: GROUP, ONE_TO_ONE"""
        if conv._conversation.type_ == hangups.schemas.ConversationType.GROUP:
            self.catalog[conv.id_]["type"] = "GROUP"
        else: 
            # conv._conversation.type_ == hangups.schemas.ConversationType.STICKY_ONE_TO_ONE
            self.catalog[conv.id_]["type"] = "ONE_TO_ONE"

        """store the off_the_record state"""
        if conv.is_off_the_record:
            self.catalog[conv.id_]["history"] = False
        else:
            self.catalog[conv.id_]["history"] = True

        if automatic_save:
            self.save_to_memory()

        logging.info("conversation_memory(): updated {} {}".format(conv.id_, conv_title))

    def remove(self, convid):
        if convid in self.catalog:
            if self.catalog[convid]["type"] == "GROUP":
                logging.info("conversation_memory(): removing {} {}".format(convid, self.catalog[convid]["title"]))
                del(self.catalog[convid])
                self.save_to_memory()
            else:
                logging.warning("conversation_memory(): cannot remove {} {} {}".format(
                    self.catalog[convid]["type"], convid, self.catalog[convid]["title"]))
        else:
            logging.warning("conversation_memory(): cannot remove {}, not found".format(convid))

    def get(self, filter=False):
        filtered = {} # function always return subset of self.catalog

        if not filter:
            # return everything
            filtered = self.catalog
        elif filter.startswith("id:"):
            # explicit request for single conv
            convid = filter[3:]
            filtered[convid] = self.catalog[convid]
        elif filter in self.catalog:
            # prioritise exact convid matches
            filtered[filter] = self.catalog[filter]
        elif filter.startswith("text:"):
            # perform case-insensitive search
            filter_lower = filter[5:].lower()
            for convid, convdata in self.catalog.items():
                if filter_lower in convdata["title"].lower():
                    filtered[convid] = convdata
        elif filter.startswith("chat_id:"):
            # return all conversations user is in
            chat_id = filter[8:]
            for convid, convdata in self.catalog.items():
                for user in convdata["users"]:
                    if user[0][0] == chat_id:
                        filtered[convid] = convdata

        return filtered

    def get_name(self, conv, truncate=False):
        """drop-in replacement for hangups.ui.utils.get_conv_name
        truncate added for backward-compatibility, should be always False
        """
        if isinstance(conv, str):
            convid = conv
        else:
            convid = conv.id_

        try:
            convdata = self.catalog[convid]
            title = convdata["title"]
        except (KeyError, AttributeError) as e:
            if not isinstance(conv, str):
                title = hangups_get_conv_name(conv, truncate=False)
            else:
                raise ValueError("could not determine conversation name")

        return title


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
            if id not in bot.conversations.catalog:
                raise ValueError("tags: conversation {} does not exist".format(id))
            tags = self.bot.conversation_memory_get(id, "tags")

        elif type == "user":
            index_type = "user"
            if not bot.conversations.get("chat_id:" + id):
                raise ValueError("tags: user {} does not exist".format(id))
            tags = self.bot.user_memory_get(id, "tags")

        elif type == "convuser":
            index_type = "user"
            [conv_id, chat_id] = id.split("|", maxsplit=1)
            if not bot.conversations.get("chat_id:" + chat_id):
                raise ValueError("tags: user {} does not exist".format(chat_id))
            if conv_id not in bot.conversations.catalog:
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
            if conv_id not in bot.conversations.catalog:
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

