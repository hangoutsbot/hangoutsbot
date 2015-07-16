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