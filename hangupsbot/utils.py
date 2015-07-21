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
        logging.info("convmem: loading users from hangups")
        for User in self.bot._user_list.get_all():
            self.store_user_memory(User, automatic_save=False, is_definitive=True)

        logging.info("convmem: loading conversations from hangups")
        for Conversation in self.bot._conv_list.get_all():
            self.update(Conversation, source="init", automatic_save=False)
 
    def load_from_memory(self):
        if self.bot.memory.exists(['convmem']):
            convs = self.bot.memory.get_by_path(['convmem'])
            logging.info("convmem(): loading conversations from memory {}".format(len(convs)))
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

                if "participants" not in self.catalog[convid]:
                    self.catalog[convid]["participants"] = [ u[0][0] for u in self.catalog[convid]["users"] ]

                """add to permanent user memory if the record is valid"""

                if len(self.catalog[convid]["users"]) > 0:
                    _added = []

                    for _u in self.catalog[convid]["users"]:
                        UserID = hangups.user.UserID(chat_id=_u[0][0], gaia_id=_u[0][1])
                        try:
                            User = self.bot._user_list._user_dict[UserID]
                            results = self.store_user_memory(
                                User, is_definitive=True, automatic_save=False)

                        except KeyError:
                            User = hangups.user.User(
                                UserID,
                                _u[1],
                                None,
                                None,
                                [],
                                False)

                            results = self.store_user_memory(
                                User, is_definitive=False, automatic_save=False)

                        if results:
                            _added.append((_u[0][0], _u[1]))

                    if len(_added) > 0:
                        logging.info("convmem(): users added when loading {}: {}".format(
                            convid, _added))


    def save_to_memory(self):
        self.bot.memory.set_by_path(['convmem'], self.catalog)
        self.bot.memory.save()


    def store_user_memory(self, User, automatic_save=True, is_definitive=False):
        self.bot.initialise_memory(User.id_.chat_id, "user_data")

        cached = False
        if self.bot.memory.exists(["user_data", User.id_.chat_id, "_hangups"]):
            cached = self.bot.memory.get_by_path(["user_data", User.id_.chat_id, "_hangups"])
            if "is_definitive" in cached and cached["is_definitive"] and is_definitive == False:
                logging.info("convmem: user {} skipped update {}".format(cached["full_name"], cached["chat_id"]))
                return False

        user_dict ={
            "chat_id": User.id_.chat_id,
            "gaia_id": User.id_.gaia_id,
            "full_name": User.full_name,
            "first_name": User.first_name,
            "photo_url": User.photo_url,
            "emails": User.emails,
            "is_self": User.is_self,
            "is_definitive": is_definitive }

        changed = False
        if cached:
            for key in list(user_dict.keys()):
                try:
                    if key == "emails":
                        if set(user_dict[key]) != set(cached[key]):
                            logging.info("convmem: user email changed {} ({})".format(User.full_name, User.id_.chat_id))
                            changed = True
                            break
                    else:
                        if user_dict[key] != cached[key]:
                            logging.info("convmem: user {} changed {} ({})".format(key, User.full_name, User.id_.chat_id))
                            changed = True
                            break

                except KeyError as e:
                    logging.info("convmem: user {} missing {} ({})".format(key, User.full_name, User.id_.chat_id))
                    changed = True
                    break
        else:
            logging.info("convmem: new user {} ({})".format(User.full_name, User.id_.chat_id))
            changed = True

        if changed:
            user_dict["updated"] = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            self.bot.memory.set_by_path(["user_data", User.id_.chat_id, "_hangups"], user_dict)

            if automatic_save:
                self.save_to_memory()

            logging.info("convmem: user {} updated {}".format(User.id_.chat_id, User.full_name))
            return True

        else:
            logging.info("convmem: user {} unchanged {}".format(User.id_.chat_id, User.full_name))
            return False



    def update(self, conv, source="unknown", automatic_save=True):
        conv_title = hangups_get_conv_name(conv)

        if conv.id_ not in self.catalog:
            self.catalog[conv.id_] = {}

        original = self.catalog[conv.id_]
        memory = {}

        """base information"""
        memory = {
            "title": conv_title,
            "source": source,
            "users" : [] }

        """store the user list"""
        memory["users"] = [[[user.id_.chat_id, user.id_.gaia_id], user.full_name ] for user in conv.users if not user.is_self]

        memory["participants"] = []
        for User in conv.users:
            if not User.is_self:
                memory["participants"].append(User.id_.chat_id)
            self.store_user_memory(User, automatic_save, is_definitive=True)

        """store the conversation type: GROUP, ONE_TO_ONE"""
        if conv._conversation.type_ == hangups.schemas.ConversationType.GROUP:
            memory["type"] = "GROUP"
        else: 
            # conv._conversation.type_ == hangups.schemas.ConversationType.STICKY_ONE_TO_ONE
            memory["type"] = "ONE_TO_ONE"

        """store the off_the_record state"""
        if conv.is_off_the_record:
            memory["history"] = False
        else:
            memory["history"] = True

        """check for taint, reduce disk trashing
            only write if its a new conversation, or there is a change in:
                title, type (should not be possible!), history, users
        """

        changed = False

        if original:
            """existing tracked conversation"""
            for key in ["title", "type", "history", "users", "participants"]:
                try:
                    if key == "participants":
                        if set(original["participants"]) != set(memory["participants"]):
                            logging.info("convmem: participants changed {} ({})".format(conv_title, conv.id_))
                            changed = True
                            break

                    elif key == "users":
                        """special processing for users list"""
                        if (set([ (u[0][0], u[0][1], u[1]) for u in original["users"] ])
                                != set([ (u[0][0], u[0][1], u[1]) for u in memory["users"] ])):
                            logging.info("convmem: users changed {} ({})".format(conv_title, conv.id_))
                            changed = True
                            break

                    else:
                        if original[key] != memory[key]:
                            logging.info("convmem: {} changed {} ({})".format(key,  conv_title, conv.id_))
                            changed = True
                            break

                except KeyError as e:
                    logging.info("convmem: missing {} {} ({})".format(key,  conv_title, conv.id_))
                    changed = True
                    break
        else:
            """new conversation"""
            logging.info("convmem: new {} ({})".format(conv_title, conv.id_))
            changed = True

        if changed:
            memory["updated"] = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            self.catalog[conv.id_] = memory

            if automatic_save:
                self.save_to_memory()

            logging.info("convmem: {} updated {}".format(conv.id_, conv_title))

        else:
            logging.info("convmem: {} unchanged {}".format(conv.id_, conv_title))


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