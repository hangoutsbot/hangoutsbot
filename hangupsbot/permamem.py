import asyncio, sys, logging, datetime

from hangups.ui.utils import get_conv_name as hangups_get_conv_name

import hangups

bot = None


logger = logging.getLogger(__name__)


def get_conv_name(conv, truncate=False):
    logger.warning("DEPRECATED: use bot.conversations.get_name()")
    return bot.conversations.get_name(conv)


def get_all_conversations(filter=False):
    logger.warning("DEPRECATED: use bot.conversations.get()")
    return bot.conversations.get(filter)


class conversation_memory:
    bot = None
    catalog = {}

    log_info_unchanged = False

    def __init__(self, bot):
        self.bot = bot
        self.catalog = {}

        self.standardise_memory()

        self.load_from_memory()

        self.load_from_hangups()

        self.bot.memory.save() # only if tainted

        logger.info("total conversations: {}".format(len(self.catalog)))

        if self.bot.memory.exists(["user_data"]):
            count_user = 0
            count_user_cached = 0
            count_user_cached_definitive = 0
            for chat_id in self.bot.memory["user_data"]:
                count_user = count_user + 1
                if "_hangups" in self.bot.memory["user_data"][chat_id]:
                    count_user_cached = count_user_cached + 1
                    if self.bot.memory["user_data"][chat_id]["_hangups"]["is_definitive"]:
                        count_user_cached_definitive = count_user_cached_definitive + 1

            logger.info("total users: {} cached: {} definitive (at start): {}".format(
                len(self.bot.memory["user_data"]), count_user, count_user_cached, count_user_cached_definitive))

        sys.modules[__name__].bot = bot # workaround for drop-ins

    def load_from_hangups(self):
        logger.info("loading {} users from hangups".format(
            len(self.bot._user_list._user_dict)))

        for User in self.bot._user_list.get_all():
            self.store_user_memory(User, automatic_save=False, is_definitive=True)

        logger.info("loading {} conversations from hangups".format(
            len(self.bot._conv_list._conv_dict)))

        for Conversation in self.bot._conv_list.get_all():
            self.update(Conversation, source="init", automatic_save=False)

    def standardise_memory(self):
        """construct the conversation memory keys and standardisethe stored structure
        devs: migrate new keys here, also add to attribute change checks in .update()
        """
        memory_updated = False

        if not self.bot.memory.exists(['convmem']):
            self.bot.memory.set_by_path(['convmem'], {})
            memory_updated = True

        convs = self.bot.memory.get_by_path(['convmem'])
        for conv_id in convs:
            conv = convs[conv_id]
            attribute_modified = False

            if "users" not in conv:
                conv["users"] = []
                attribute_modified = True

            if "type" not in conv:
                conv["type"] = "unknown"
                attribute_modified = True

            if conv["type"] == "unknown":
                """intelligently guess the type"""
                if len(conv["users"]) > 1:
                    conv["type"] = "GROUP"
                    attribute_modified = True
                else:
                    if self.bot.memory.exists(["user_data"]):
                        """inefficient one-off search"""
                        for chat_id in self.bot.memory["user_data"]:
                            if self.bot.memory.exists(["user_data", chat_id, "1on1"]):
                                if self.bot.memory["user_data"][chat_id]["1on1"] == conv_id:
                                    conv["type"] = "ONE_TO_ONE"
                                    attribute_modified = True
                                    break

            if "history" not in conv:
                conv["history"] = True
                attribute_modified = True

            if "participants" not in conv:
                if conv["users"]:
                    conv["participants"] = [ u[0][0] for u in conv["users"] ]
                else:
                    conv["participants"] = []
                attribute_modified = True

            if attribute_modified:
                self.bot.memory.set_by_path(['convmem', conv_id], conv)
                memory_updated = True

        return memory_updated


    def load_from_memory(self):
        """load "persisted" conversations from memory.json into self.catalog
        complete internal user list by using (legacy) "users" and "participants" keys
        """

        if self.bot.memory.exists(['convmem']):
            convs = self.bot.memory.get_by_path(['convmem'])
            logger.info("loading {} conversations from memory".format(len(convs)))

            _users_added = {}
            _users_incomplete = {}
            _users_unknown = {}

            _users_to_fetch = []

            for convid in convs:
                self.catalog[convid] = convs[convid]

                """legacy "users" list can construct a User with chat_id, full_name"""

                if "users" in self.catalog[convid] and len(self.catalog[convid]["users"]) > 0:

                    for _u in self.catalog[convid]["users"]:
                        UserID = hangups.user.UserID(chat_id=_u[0][0], gaia_id=_u[0][1])

                        try:
                            User = self.bot._user_list._user_dict[UserID]
                            results = self.store_user_memory(User, is_definitive=True, automatic_save=False)

                        except KeyError:
                            User = hangups.user.User(
                                UserID,
                                _u[1],
                                None,
                                None,
                                [],
                                False)
                            results = self.store_user_memory(User, is_definitive=False, automatic_save=False)

                        if results:
                            _users_added[ _u[0][0] ] = _u[1]

                """simplified "participants" list has insufficient data to construct a passable User"""

                if "participants" in self.catalog[convid] and len(self.catalog[convid]["participants"]) > 0:

                    for _chat_id in self.catalog[convid]["participants"]:
                        try:
                            UserID = hangups.user.UserID(chat_id=_chat_id, gaia_id=_chat_id)
                            User = self.bot._user_list._user_dict[UserID]
                            results = self.store_user_memory(User, is_definitive=True, automatic_save=False)
                            if results:
                                _users_added[_chat_id] = User.full_name

                        except KeyError:
                            cached = False
                            if self.bot.memory.exists(["user_data", _chat_id, "_hangups"]):
                                cached = self.bot.memory.get_by_path(["user_data", _chat_id, "_hangups"])
                                if cached["is_definitive"]:
                                    # ignore definitive entries
                                    continue

                            if cached:
                                _users_incomplete[_chat_id] = cached["full_name"]
                            else:
                                _users_unknown[_chat_id] = "unidentified"

                            _users_to_fetch.append(_chat_id)

            if len(_users_added) > 0:
                logger.info("added users: {}".format(_users_added))

            if len(_users_incomplete) > 0:
                logger.info("incomplete users: {}".format(_users_incomplete))

            if len(_users_unknown) > 0:
                logger.warning("unknown users: {}".format(_users_unknown))

            """attempt to rebuilt the user data with hangups.client.getentitybyid()"""

            if len(_users_to_fetch) > 0:
                asyncio.async(
                    self.get_users_from_query(_users_to_fetch)
                ).add_done_callback(lambda future: future.result())


    @asyncio.coroutine
    def get_users_from_query(self, chat_ids):
        chat_ids = list(set(chat_ids))
        logger.debug("getentitybyid(): {}".format(chat_ids))

        response = yield from bot._client.getentitybyid(chat_ids)

        updated_users = 0
        for _user in response.entities:
            UserID = hangups.user.UserID(chat_id=_user.id_.chat_id, gaia_id=_user.id_.gaia_id)
            User = hangups.user.User(
                UserID,
                _user.properties.display_name,
                _user.properties.first_name,
                _user.properties.photo_url,
                _user.properties.emails,
                False)

            if self.store_user_memory(User, is_definitive=True, automatic_save=False):
                updated_users = updated_users + 1

        if updated_users > 0:
            self.bot.memory.save()
            logger.info("getentitybyid(): {} users updated".format(updated_users))


    def store_user_memory(self, User, automatic_save=True, is_definitive=False):
        """update user memory based on supplied hangups User
        conservative writing: on User attribute changes only
        returns True on User change, False on no changes
        """
        self.bot.initialise_memory(User.id_.chat_id, "user_data")

        cached = False
        if self.bot.memory.exists(["user_data", User.id_.chat_id, "_hangups"]):
            cached = self.bot.memory.get_by_path(["user_data", User.id_.chat_id, "_hangups"])
            if "is_definitive" in cached and cached["is_definitive"] and is_definitive == False:
                if self.log_info_unchanged:
                    logger.info("skipped user update: {} ({})".format(cached["full_name"], cached["chat_id"]))
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
                            logger.info("user email changed {} ({})".format(User.full_name, User.id_.chat_id))
                            changed = True
                            break
                    else:
                        if user_dict[key] != cached[key]:
                            logger.info("user {} changed {} ({})".format(key, User.full_name, User.id_.chat_id))
                            changed = True
                            break

                except KeyError as e:
                    logger.info("user {} missing {} ({})".format(key, User.full_name, User.id_.chat_id))
                    changed = True
                    break
        else:
            logger.info("new user {} ({})".format(User.full_name, User.id_.chat_id))
            changed = True

        if changed:
            user_dict["updated"] = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            self.bot.memory.set_by_path(["user_data", User.id_.chat_id, "_hangups"], user_dict)

            if automatic_save:
                self.bot.memory.save()

            logger.info("user {} updated {}".format(User.id_.chat_id, User.full_name))

        else:
            if self.log_info_unchanged:
                logger.info("user {} unchanged".format(User.id_.chat_id))

        return changed


    def update(self, conv, source="unknown", automatic_save=True):
        """update conversation memory based on supplied hangups Conversation
        conservative writing: on changed Conversation and/or User attribute changes
        return True on Conversation/User change, False on no changes
        """
        conv_title = hangups_get_conv_name(conv)

        original = {}
        if self.bot.memory.exists(["convmem", conv.id_]):
            original = self.bot.memory.get_by_path(["convmem", conv.id_])

        memory = {}

        """base information"""
        memory = {
            "title": conv_title,
            "source": source,
            "users" : [] }

        """user list + user records writing"""

        memory["users"] = [[[user.id_.chat_id, user.id_.gaia_id], user.full_name ] for user in conv.users if not user.is_self]

        memory["participants"] = []

        _users_to_fetch = [] # track possible unknown users from hangups Conversation
        users_changed = False # track whether memory["user_data"] was changed

        for User in conv.users:
            if not User.is_self:
                memory["participants"].append(User.id_.chat_id)

            if User.full_name.upper() == "UNKNOWN":
                _modified = self.store_user_memory(User, automatic_save=False, is_definitive=False)
                _users_to_fetch.append(User.id_.chat_id)
            else:
                _modified = self.store_user_memory(User, automatic_save=False, is_definitive=True)

            if _modified:
                users_changed = True

        if len(_users_to_fetch) > 0:
            logger.warning("unknown users returned from {} ({}): {}".format(conv_title, conv.id_, _users_to_fetch))
            asyncio.async(
                self.get_users_from_query(_users_to_fetch)
            ).add_done_callback(lambda future: future.result())

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

        conv_changed = False

        if original:
            """existing tracked conversation"""
            for key in ["title", "type", "history", "users", "participants"]:
                try:
                    if key == "participants":
                        if set(original["participants"]) != set(memory["participants"]):
                            logger.info("conv participants changed {} ({})".format(conv_title, conv.id_))
                            conv_changed = True
                            break

                    elif key == "users":
                        """special processing for users list"""
                        if (set([ (u[0][0], u[0][1], u[1]) for u in original["users"] ])
                                != set([ (u[0][0], u[0][1], u[1]) for u in memory["users"] ])):
                            logger.info("conv users changed {} ({})".format(conv_title, conv.id_))
                            conv_changed = True
                            break

                    else:
                        if original[key] != memory[key]:
                            logger.info("conv {} changed {} ({})".format(key,  conv_title, conv.id_))
                            conv_changed = True
                            break

                except KeyError as e:
                    logger.info("conv missing {} {} ({})".format(key,  conv_title, conv.id_))
                    conv_changed = True
                    break
        else:
            """new conversation"""
            logger.info("new conv {} ({})".format(conv_title, conv.id_))
            conv_changed = True

        if conv_changed:
            memory["updated"] = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            self.bot.memory.set_by_path(["convmem", conv.id_], memory)

            self.catalog[conv.id_] = memory

            if automatic_save:
                # if users_changed this would write those changes as well
                self.bot.memory.save()

            logger.info("conv {} updated {}".format(conv.id_, conv_title))

        else:
            if self.log_info_unchanged:
                logger.info("conv {} unchanged".format(conv.id_))

            if users_changed:
                logger.info("users from conv {} changed".format(conv.id_))
                self.bot.memory.save()

            elif self.log_info_unchanged:
                logger.info("users from conv {} unchanged".format(conv.id_))

        return conv_changed or users_changed


    def remove(self, conv_id):
        if self.bot.memory.exists(["convmem", conv_id]):
            _cached = self.bot.memory.get_by_path(["convmem", conv_id])
            if _cached["type"] == "GROUP":
                logger.info("removing conv: {} {}".format(conv_id, _cached["title"]))
                self.bot.memory.pop_by_path(["convmem", conv_id])
                del self.catalog[conv_id]

            else:
                logger.warning("cannot remove conv: {} {} {}".format(
                    _cached["type"], conv_id, _cached["title"]))

        else:
            logger.warning("cannot remove: {}, not found".format(conv_id))

        self.bot.memory.save()


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
            filter_chat_id = filter[8:]
            for convid, convdata in self.catalog.items():
                for chat_id in convdata["participants"]:
                    if filter_chat_id == chat_id:
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