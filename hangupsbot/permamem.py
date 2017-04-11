import asyncio, datetime, logging, random, re

import hangups

import hangups_shim

bot = None


logger = logging.getLogger(__name__)


def name_from_hangups_conversation(conv):
    """get the name for supplied hangups conversation
    based on hangups.ui.utils.get_conv_name, except without the warnings
    """
    if conv.name is not None:
        return conv.name
    else:
        participants = sorted(
            (user for user in conv.users if not user.is_self),
            key=lambda user: user.id_
        )
        names = [user.first_name for user in participants]
        if len(participants) == 0:
            return "Empty Conversation"
        if len(participants) == 1:
            return participants[0].full_name
        else:
            return ', '.join(names)


@asyncio.coroutine
def initialise_permanent_memory(bot):
    permamem = conversation_memory(bot)

    yield from permamem.standardise_memory()
    yield from permamem.load_from_memory()
    yield from permamem.load_from_hangups()

    permamem.stats()

    permamem.bot.memory.save() # only if tainted

    return permamem


class conversation_memory:
    bot = None
    catalog = {}

    log_info_unchanged = False

    def __init__(self, bot):
        self.bot = bot
        self.catalog = {}

    def stats(self):
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
                count_user, count_user_cached, count_user_cached_definitive))


    @asyncio.coroutine
    def standardise_memory(self):
        """construct the conversation memory keys and standardise the stored structure
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

            # remove obsolete users list
            if "users" in conv:
                del conv["users"]
                attribute_modified = True

            if "type" not in conv:
                conv["type"] = "unknown"
                attribute_modified = True

            if "history" not in conv:
                conv["history"] = True
                attribute_modified = True

            if "participants" not in conv:
                conv["participants"] = []
                attribute_modified = True

            if conv["type"] == "unknown":
                """intelligently guess the type"""
                if len(conv["participants"]) > 1:
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

            if attribute_modified:
                self.bot.memory.set_by_path(['convmem', conv_id], conv)
                memory_updated = True

        return memory_updated

    @asyncio.coroutine
    def load_from_memory(self):
        """load "persisted" conversations from memory.json into self.catalog
        complete internal user list by using "participants" keys
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
                                    if cached["full_name"].upper() == "UNKNOWN" and cached["full_name"] == cached["first_name"]:
                                        # XXX: crappy way to detect hangups unknown users
                                        logger.debug("user {} needs refresh".format(_chat_id))
                                    else:
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
                yield from self.get_users_from_query(_users_to_fetch)


    @asyncio.coroutine
    def load_from_hangups(self):
        logger.info("loading {} users from hangups".format(
            len(self.bot._user_list._user_dict)))

        for User in self.bot._user_list.get_all():
            self.store_user_memory(User, automatic_save=False, is_definitive=True)

        logger.info("loading {} conversations from hangups".format(
            len(self.bot._conv_list._conv_dict)))

        for Conversation in self.bot._conv_list.get_all():
            yield from self.update(Conversation, source="init", automatic_save=False)


    @asyncio.coroutine
    def get_users_from_query(self, chat_ids, batch_max=20):
        """retrieve definitive user data by requesting it from the server"""

        chat_ids = list(set(chat_ids))

        chunks = [ chat_ids[i:i+batch_max]
                   for i in range(0, len(chat_ids), batch_max) ]

        updated_users = 0

        for chunk in chunks:
            logger.debug("getentitybyid(): {}".format(chunk))

            try:
                _request = hangups.hangouts_pb2.GetEntityByIdRequest(
                    request_header=self.bot._client.get_request_header(),
                    batch_lookup_spec=[ hangups.hangouts_pb2.EntityLookupSpec( gaia_id=chat_id) 
                                        for chat_id in chunk ])

                _response = yield from self.bot._client.get_entity_by_id(_request)

                for _user in _response.entity:
                    UserID = hangups.user.UserID(chat_id=_user.id.chat_id, gaia_id=_user.id.gaia_id)
                    User = hangups.user.User(
                        UserID,
                        _user.properties.display_name,
                        _user.properties.first_name,
                        _user.properties.photo_url,
                        list(_user.properties.email), # repeated field
                        False)

                    """this function usually called because hangups user list is incomplete, so help fill it in as well"""
                    logger.debug("updating hangups user list {} ({})".format(User.id_.chat_id, User.full_name))
                    self.bot._user_list._user_dict[User.id_] = User

                    if self.store_user_memory(User, is_definitive=True, automatic_save=False):
                        updated_users = updated_users + 1

            except hangups.exceptions.NetworkError as e:
                logger.exception("getentitybyid(): FAILED for chunk {}".format(chunk))

        if updated_users > 0:
            self.bot.memory.save()
            logger.info("getentitybyid(): {} users updated".format(updated_users))
        else:
            if self.log_info_unchanged:
                logger.info("getentitybyid(): no change")

        return updated_users


    def store_user_memory(self, User, automatic_save=True, is_definitive=False):
        """update user memory based on supplied hangups User
        conservative writing: on User attribute changes only
        returns True on User change, False on no changes
        """

        """in the event hangups returned an "unknown" user, turn off the is_definitive flag"""
        if User.full_name.upper() == "UNKNOWN" and User.first_name == User.full_name and is_definitive:
            logger.debug("user {} ({}) not definitive".format(User.id_.chat_id, User.full_name))
            is_definitive = False

        """load existing cached user, reject update if cache is_definitive and supplied is not"""
        cached = False
        if self.bot.memory.exists(["user_data", User.id_.chat_id, "_hangups"]):
            cached = self.bot.memory.get_by_path(["user_data", User.id_.chat_id, "_hangups"])
            if "is_definitive" in cached and cached["is_definitive"] and is_definitive == False:
                if self.log_info_unchanged:
                    logger.info("skipped user update: {} ({})".format(cached["full_name"], cached["chat_id"]))
                return False

        changed = False

        if self.bot.initialise_memory(User.id_.chat_id, "user_data"):
            changed = True

        user_dict ={
            "chat_id": User.id_.chat_id,
            "gaia_id": User.id_.gaia_id,
            "full_name": User.full_name,
            "first_name": User.first_name,
            "photo_url": User.photo_url,
            "emails": list(User.emails),
            "is_self": User.is_self,
            "is_definitive": is_definitive }

        if cached:
            # XXX: no way to detect hangups fallback users reliably,
            # XXX:   prioritise existing cached attributes

            if not user_dict["photo_url"] and "photo_url" in cached and cached["photo_url"]:
                user_dict["photo_url"] = cached["photo_url"]

            if not user_dict["emails"] and "emails" in cached and cached["emails"]:
                user_dict["emails"] = cached["emails"]

            """scan for differences between supplied and cached"""

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


    @asyncio.coroutine
    def update(self, conv, source="unknown", automatic_save=True):
        """update conversation memory based on supplied hangups Conversation
        conservative writing: on changed Conversation and/or User attribute changes
        return True on Conversation/User change, False on no changes
        """
        conv_title = name_from_hangups_conversation(conv)

        original = {}
        if self.bot.memory.exists(["convmem", conv.id_]):
            original = self.bot.memory.get_by_path(["convmem", conv.id_])

        memory = {}

        """base information"""
        memory = {
            "title": conv_title,
            "source": source,
            "participants": [] }

        """user list + user records writing"""

        memory["participants"] = []

        _users_to_fetch = [] # track possible unknown users from hangups Conversation
        users_changed = False # track whether memory["user_data"] was changed

        for User in conv.users:
            if not User.is_self:
                memory["participants"].append(User.id_.chat_id)

            if User.full_name.upper() == "UNKNOWN" and User.first_name == User.full_name:
                # XXX: crappy way to detect hangups users
                _modified = self.store_user_memory(User, automatic_save=False, is_definitive=False)
                _users_to_fetch.append(User.id_.chat_id)

            elif not User.photo_url and not User.emails:
                # XXX: crappy way to detect fallback users
                # XXX:  users with no photo_url, emails will always get here, definitive or not
                _modified = self.store_user_memory(User, automatic_save=False, is_definitive=False)

            else:
                _modified = self.store_user_memory(User, automatic_save=False, is_definitive=True)

            if _modified:
                users_changed = True

        if len(_users_to_fetch) > 0:
            logger.warning("unknown users returned from {} ({}): {}".format(conv_title, conv.id_, _users_to_fetch))
            yield from self.get_users_from_query(_users_to_fetch)

        """store the conversation type: GROUP, ONE_TO_ONE"""
        if conv._conversation.type == hangups_shim.schemas.ConversationType.GROUP:
            memory["type"] = "GROUP"
        else:
            # conv._conversation.type_ == hangups_shim.schemas.ConversationType.STICKY_ONE_TO_ONE
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
            for key in ["title", "type", "history", "participants"]:
                try:
                    if key == "participants":
                        if set(original["participants"]) != set(memory["participants"]):
                            logger.info("conv participants changed {} ({})".format(conv_title, conv.id_))
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


    def get(self, filter=""):
        """get dictionary of conversations that matches filter term(s) (ALL if not supplied)
        supports sequential boolean operations, each term must be enclosed with brackets ( ... )
        """

        terms = []
        raw_filter = filter.strip()
        operator = "start"
        while raw_filter.startswith("("):
            tokens = re.split(r"(?<!\\)(?:\\\\)*\)", raw_filter, maxsplit=1)
            terms.append([operator, tokens[0][1:]])
            if len(tokens) == 2:
                raw_filter = tokens[1]
                if not raw_filter:
                    # finished consuming entire string
                    pass
                elif re.match(r"^\s*and\s*\(", raw_filter, re.IGNORECASE):
                    operator = "and"
                    raw_filter = tokens[1][raw_filter.index('('):].strip()
                elif re.match(r"^\s*or\s*\(", raw_filter, re.IGNORECASE):
                    operator = "or"
                    raw_filter = tokens[1][raw_filter.index('('):].strip()
                else:
                    raise ValueError("invalid boolean operator near \"{}\"".format(raw_filter.strip()))

        if raw_filter or len(terms)==0:
            # second condition is to ensure at least one term, even if blank
            terms.append([operator, raw_filter])

        sourcelist = self.catalog.copy()
        matched = {}

        logger.debug("get(): {}".format(terms))

        for operator, term in terms:
            if operator == "and":
                sourcelist = matched
                matched = {}

            """extra search term types added here"""

            if not term:
                # return everything
                matched = sourcelist

            elif term.startswith("id:"):
                # explicit request for single conv
                convid = term[3:]
                matched[convid] = sourcelist[convid]

            elif term in sourcelist:
                # prioritise exact convid matches
                matched[term] = sourcelist[term]

            elif term.startswith("text:"):
                # perform case-insensitive search
                filter_lower = term[5:].lower()
                for convid, convdata in sourcelist.items():
                    title_lower = convdata["title"].lower()
                    if( filter_lower in title_lower
                            or filter_lower in title_lower.replace(" ", "") ):
                        matched[convid] = convdata

            elif term.startswith("chat_id:"):
                # return all conversations user is in
                filter_chat_id = term[8:]
                for convid, convdata in sourcelist.items():
                    for chat_id in convdata["participants"]:
                        if filter_chat_id == chat_id:
                            matched[convid] = convdata

            elif term.startswith("tag:"):
                # return all conversations with the tag
                filter_tag = term[4:]
                if filter_tag in self.bot.tags.indices["tag-convs"]:
                    for conv_id in self.bot.tags.indices["tag-convs"][filter_tag]:
                        if conv_id in sourcelist:
                            matched[conv_id] = sourcelist[conv_id]

            elif term.startswith("type:"):
                # return all conversations with matching type (case-insensitive)
                filter_type = term[5:]
                for convid, convdata in sourcelist.items():
                    if convdata["type"].lower() == filter_type.lower():
                        matched[convid] = convdata

            elif term.startswith("minusers:"):
                # return all conversations with number of users or higher
                filter_numusers = term[9:]
                for convid, convdata in sourcelist.items():
                    if len(convdata["participants"]) >= int(filter_numusers):
                        matched[convid] = convdata

            elif term.startswith("maxusers:"):
                # return all conversations with number of users or lower
                filter_numusers = term[9:]
                for convid, convdata in sourcelist.items():
                    if len(convdata["participants"]) <= int(filter_numusers):
                        matched[convid] = convdata

            elif term.startswith("random:"):
                # return random conversations based on selection threshold
                filter_random = term[7:]
                for convid, convdata in sourcelist.items():
                    if random.random() <= float(filter_random):
                        matched[convid] = convdata

        return matched

    def get_name(self, conv, truncate=False, fallback_string=False):
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
                title = name_from_hangups_conversation(conv)
            else:
                if fallback_string:
                    return fallback_string
                else:
                    raise ValueError("could not determine conversation name")

        return title
