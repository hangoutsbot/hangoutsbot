import logging, re

from commands import command


logger = logging.getLogger(__name__)


class tags:
    regex_allowed = "a-z0-9._\-" # +command.deny_prefix

    wildcard = { "conversation": "*",
                 "user": "*",
                 "group": "GROUP",
                 "one2one": "ONE_TO_ONE" }

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

        logger.info("refreshed")

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
                if len(self.indices[tag_to_object][tag]) == 0:
                    # remove key entirely it its empty
                    del(self.indices[tag_to_object][tag])

        if id in self.indices[object_to_tag]:
            if tag in self.indices[object_to_tag][id]:
                self.indices[object_to_tag][id].remove(tag)
                if len(self.indices[object_to_tag][id]) == 0:
                    # remove key entirely it its empty
                    del(self.indices[object_to_tag][id])

    def update(self, type, id, action, tag):
        updated = False
        tags = None

        if type == "conv":
            index_type = "conv"

            if( id not in self.bot.conversations.catalog and
                  id not in ( self.wildcard["group"],
                              self.wildcard["one2one"],
                              self.wildcard["conversation"]) ):

                raise ValueError("conversation {} does not exist".format(id))

            tags = self.bot.conversation_memory_get(id, "tags")

        elif type == "user":
            index_type = "user"

            if( not self.bot.memory.exists(["user_data", id]) and
                  id != self.wildcard["user"] ):

                raise ValueError("user {} is invalid".format(id))

            tags = self.bot.user_memory_get(id, "tags")

        elif type == "convuser":
            index_type = "user"
            [conv_id, chat_id] = id.split("|", maxsplit=1)

            if( conv_id not in self.bot.conversations.catalog and
                  conv_id not in (self.wildcard["group"], self.wildcard["one2one"]) ):

                raise ValueError("conversation {} is invalid".format(conv_id))

            if( not self.bot.memory.exists(["user_data", chat_id]) and
                  chat_id != self.wildcard["user"] ):

                raise ValueError("user {} is invalid".format(chat_id))

            tags_users = self.bot.conversation_memory_get(conv_id, "tags-users")

            if not tags_users:
                tags_users = {}

            if chat_id in tags_users:
                tags = tags_users[chat_id]

        else:
            raise TypeError("unhandled read type {}".format(type))

        if not tags:
            tags = []

        if action == "set":
            # XXX: placed here so users can still remove previous invalid tags
            allowed = "^[{}{}]*$".format(self.regex_allowed, re.escape(command.deny_prefix))
            if not re.match(allowed, tag, re.IGNORECASE):
                raise ValueError("tag contains invalid characters")

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
            raise ValueError("unrecognised action {}".format(action))

        if updated:
            if type == "conv":
                self.bot.conversation_memory_set(id, "tags", tags)

            elif type == "user":
                self.bot.user_memory_set(id, "tags", tags)

            elif type == "convuser":
                tags_users[chat_id] = tags
                self.bot.conversation_memory_set(conv_id, "tags-users", tags_users)

            else:
                raise TypeError("unhandled update type {}".format(type))

            logger.info("{}/{} action={} value={}".format(type, id, action, tag))
        else:
            logger.info("{}/{} action={} value={} [NO CHANGE]".format(type, id, action, tag))

        return updated


    def add(self, type, id, tag):
        """add tag to (type=conv|user|convuser) id"""
        return self.update(type, id, "set", tag)


    def remove(self, type, id, tag):
        """remove tag from (type=conv|user|convuser) id"""
        return self.update(type, id, "remove", tag)


    def purge(self, type, id):
        """completely remove the specified type (type="user|convuser|conv|tag|usertag|convtag") and label"""
        remove = []

        if type == "user" or type == "convuser":
            for key in self.indices["user-tags"]:

                match_user = (type == "user" and (key == id or id=="ALL"))
                    # runs if type=="user"
                match_convuser = (key.endswith("|" + id) or (id=="ALL" and "|" in key))
                    # runs if type=="user" or type=="convuser"

                if match_user or match_convuser:
                    for tag in self.indices["user-tags"][key]:
                        remove.append(("user" if match_user else "convuser", key, tag))

        elif type == "conv":
            for key in self.indices["conv-tags"]:
                if key == id or id == "ALL":
                    for tag in self.indices["conv-tags"][key]:
                        remove.append(("conv", key, tag))

        elif type == "tag" or type == "usertag" or type == "convtag":
            if type == "usertag":
                _types = ["user"]
            elif type == "convtag":
                _types = ["conv"]
            else:
                # type=="tag"
                _types = ["conv", "user"]

            for _type in _types:
                _index_name = "tag-{}s".format(_type)
                for tag in self.indices[_index_name]:
                    if tag == id or id == "ALL":
                        for key in self.indices[_index_name][tag]:
                            remove.append((_type, key, id))

        else:
            raise TypeError("{}".format(type))

        records_removed = 0
        if remove:
            for args in remove:
                if self.remove(*args):
                    records_removed = records_removed + 1

        return records_removed


    def convactive(self, conv_id):
        """return active tags for conv_id, or generic GROUP, ONE_TO_ONE keys"""

        active_tags = []
        check_keys = []

        if conv_id in self.bot.conversations.catalog:
            check_keys.extend([ conv_id ])
            # additional overrides based on type of conversation
            conv_type = self.bot.conversations.catalog[conv_id]["type"]
            if conv_type == "GROUP":
                check_keys.extend([ self.wildcard["group"] ])
            elif conv_type == "ONE_TO_ONE" :
                check_keys.extend([ self.wildcard["one2one"] ])
            check_keys.extend([ self.wildcard["conversation"] ])
        else:
            logger.warning("convactive: conversation {} does not exist".format(conv_id))

        for _key in check_keys:
            if _key in self.indices["conv-tags"]:
                active_tags.extend(self.indices["conv-tags"][_key])
                active_tags = list(set(active_tags))
                if "tagging-merge" not in active_tags:
                    break

        return active_tags


    def useractive(self, chat_id, conv_id="*"):
        """return active tags of user for current conv_id if supplied, globally if not"""

        active_tags = []
        check_keys = []

        if self.bot.memory.exists(["user_data", chat_id]):
            if conv_id != "*":
                if conv_id in self.bot.conversations.catalog:
                    # per_conversation_user_override_keys
                    check_keys.extend([ conv_id + "|" + chat_id,
                                        conv_id + "|" + self.wildcard["user"] ])

                    # additional overrides based on type of conversation
                    if self.bot.conversations.catalog[conv_id]["type"] == "GROUP":
                        check_keys.extend([ self.wildcard["group"] + "|" + chat_id,
                                            self.wildcard["group"] + "|" + self.wildcard["user"] ])
                    else:
                        check_keys.extend([ self.wildcard["one2one"] + "|" + chat_id,
                                            self.wildcard["one2one"] + "|" + self.wildcard["user"] ])

                else:
                    logger.warning("useractive: conversation {} does not exist".format(conv_id))

            check_keys.extend([ chat_id,
                                self.wildcard["user"] ])

        else:
            logger.warning("useractive: user {} does not exist".format(chat_id))

        for _key in check_keys:
            if _key in self.indices["user-tags"]:
                active_tags.extend(self.indices["user-tags"][_key])
                active_tags = list(set(active_tags))
                if "tagging-merge" not in active_tags:
                    break

        return active_tags


    def userlist(self, conv_id, tags=False):
        """return dict of participating chat_ids to tags, optionally filtered by tag/list of tags"""

        if isinstance(tags, str):
            tags = [tags]

        userlist = []
        try:
            userlist = self.bot.conversations.catalog[conv_id]["participants"]
        except KeyError:
            logger.warning("userlist: conversation {} does not exist".format(conv_id))

        results = {}
        for chat_id in userlist:
            user_tags = self.useractive(chat_id, conv_id)
            if tags and not set(tags).issubset(set(user_tags)):
                continue
            results[chat_id] = user_tags
        return results
