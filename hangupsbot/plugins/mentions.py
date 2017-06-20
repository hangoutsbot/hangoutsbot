import asyncio, logging, re, string

from pushbullet import PushBullet

import plugins

from utils import remove_accents


logger = logging.getLogger(__name__)


nicks = {}


def _initialise(bot):
    _migrate_mention_config_to_memory(bot)
    plugins.register_handler(_handle_mention, "message")
    plugins.register_user_command(["pushbulletapi", "setnickname", "bemorespecific"])
    plugins.register_admin_command(["mention"])


def _migrate_mention_config_to_memory(bot):
    # migrate pushbullet apikeys to memory.json
    if bot.config.exists(["pushbullet"]):
        api_settings = bot.config.get("pushbullet")
        for user_chat_id in api_settings:
            user_api = api_settings[user_chat_id]
            logger.debug("migrating user {} = {} to memory.json".format(user_chat_id, user_api))
            bot.initialise_memory(user_chat_id, "user_data")
            bot.memory.set_by_path(["user_data", user_chat_id, "pushbullet"], user_api)
        del bot.config["pushbullet"]
        bot.memory.save()
        bot.config.save()
        logger.debug("pushbullet config migrated")


def _handle_mention(bot, event, command):
    """handle @mention"""
    occurrences = [word for word in set(event.text.split()) if word.startswith('@')]
    if len(occurrences) > 0:
        for word in occurrences:
            # strip all special characters
            cleaned_name = ''.join(e for e in word if e.isalnum() or e in ["-"])
            yield from command.run(bot, event, *["mention", cleaned_name])


def _user_has_dnd(bot, user_id):
    try:
        return bot.call_shared("dnd.user_check", user_id) # shared dnd check
    except KeyError:
        logger.warning("mentions: falling back to legacy _user_has_dnd()")
        initiator_has_dnd = False
        if bot.memory.exists(["donotdisturb"]):
            donotdisturb = bot.memory.get('donotdisturb')
            if user_id in donotdisturb:
                initiator_has_dnd = True
        return initiator_has_dnd


def mention(bot, event, *args):
    """alert a @mentioned user"""

    """allow mentions to be disabled via global or per-conversation config"""
    config_mentions_enabled = False if bot.get_config_suboption(event.conv.id_, 'mentions.enabled') is False else True
    if not config_mentions_enabled:
        logger.info("mentions explicitly disabled by config for {}".format(event.conv_id))
        return

    """minimum length check for @mention"""
    minimum_length = bot.get_config_suboption(event.conv_id, 'mentionminlength')
    if not minimum_length:
        minimum_length = 2
    username = args[0].strip()
    if len(username) < minimum_length:
        logger.debug("@mention from {} ({}) too short (== '{}')".format(event.user.full_name, event.user.id_.chat_id, username))
        return

    users_in_chat = event.conv.users
    mention_chat_ids = []

    """sync room support"""
    if bot.get_config_option('syncing_enabled'):
        sync_room_list = bot.get_config_option('sync_rooms')
        if sync_room_list:
            """scan through each room group"""
            for rooms_group in sync_room_list:
                if event.conv_id in rooms_group:
                    """current conversation is part of a syncroom group, add "external" users"""
                    for syncedroom in rooms_group:
                        if event.conv_id is not syncedroom:
                            users_in_chat += bot.get_users_in_conversation(syncedroom)
                    users_in_chat = list(set(users_in_chat)) # make unique
                    logger.debug("@mention in a syncroom: {} user(s) present".format(len(users_in_chat)))
                    break

    """
    /bot mention <fragment> test
    """
    noisy_mention_test = False
    if len(args) == 2 and args[1] == "test":
        noisy_mention_test = True

    initiator_has_dnd = _user_has_dnd(bot, event.user.id_.chat_id)

    """
    quidproquo: users can only @mention if they themselves are @mentionable (i.e. have a 1-on-1 with the bot)
    """
    conv_1on1_initiator = yield from bot.get_1to1(event.user.id_.chat_id, context={ 'initiator_convid': event.conv_id })
    if bot.get_config_option("mentionquidproquo"):
        if conv_1on1_initiator:
            if initiator_has_dnd:
                logger.info("quidproquo: user {} ({}) has DND active".format(event.user.full_name, event.user.id_.chat_id))
                if noisy_mention_test or bot.get_config_suboption(event.conv_id, 'mentionerrors'):
                    yield from bot.coro_send_message(
                        event.conv,
                        _("<b>{}</b>, you cannot @mention anyone until your DND status is toggled off.").format(
                            event.user.full_name))
                return
            else:
                logger.debug("quidproquo: user {} ({}) has 1-on-1".format(event.user.full_name, event.user.id_.chat_id))
        else:
            logger.info("quidproquo: user {} ({}) has no 1-on-1".format(event.user.full_name, event.user.id_.chat_id))
            if noisy_mention_test or bot.get_config_suboption(event.conv_id, 'mentionerrors'):
                yield from bot.coro_send_message(
                    event.conv,
                    _("<b>{}</b> cannot @mention anyone until they say something to me first.").format(
                        event.user.full_name))
            return

    """track mention statistics"""
    user_tracking = {
      "mentioned":[],
      "ignored":[],
      "failed": {
        "pushbullet": [],
        "one2one": [],
      }
    }

    """
    begin mentioning users as long as they exist in the current conversation...
    """

    conversation_name = bot.conversations.get_name(event.conv)
    logger.info("@mention '{}' in '{}' ({})".format(username, conversation_name, event.conv.id_))
    username_lower = username.lower()
    username_upper = username.upper()

    """is @all available globally/per-conversation/initiator?"""
    if username_lower == "all":
        if not bot.get_config_suboption(event.conv.id_, 'mentionall'):

            """global toggle is off/not set, check admins"""
            logger.debug("@all in {}: disabled/unset global/per-conversation".format(event.conv.id_))
            admins_list = bot.get_config_suboption(event.conv_id, 'admins')
            if event.user_id.chat_id not in admins_list:

                """initiator is not an admin, check whitelist"""
                logger.debug("@all in {}: user {} ({}) is not admin".format(event.conv.id_, event.user.full_name, event.user.id_.chat_id))
                all_whitelist = bot.get_config_suboption(event.conv_id, 'mentionallwhitelist')
                if all_whitelist is None or event.user_id.chat_id not in all_whitelist:

                    logger.warning("@all in {}: user {} ({}) blocked".format(event.conv.id_, event.user.full_name, event.user.id_.chat_id))
                    if conv_1on1_initiator:
                        yield from bot.coro_send_message(
                            conv_1on1_initiator,
                            _("You are not allowed to mention all users in <b>{}</b>").format(
                                conversation_name))
                    if noisy_mention_test or bot.get_config_suboption(event.conv_id, 'mentionerrors'):
                        yield from bot.coro_send_message(
                            event.conv,
                            _("<b>{}</b> blocked from mentioning all users").format(
                                event.user.full_name))
                    return
                else:
                    logger.info("@all in {}: allowed, {} ({}) is whitelisted".format(event.conv.id_, event.user.full_name, event.user.id_.chat_id))
            else:
                logger.info("@all in {}: allowed, {} ({}) is an admin".format(event.conv.id_, event.user.full_name, event.user.id_.chat_id))
        else:
            logger.info("@all in {}: enabled global/per-conversation".format(event.conv.id_))

    """generate a list of users to be @mentioned"""
    exact_nickname_matches = []
    exact_fragment_matches = []
    mention_list = []
    for u in users_in_chat:

        # mentions also checks nicknames if one is configured
        #  exact matches only! see following IF block
        nickname = ""
        nickname_lower = ""
        if bot.memory.exists(['user_data', u.id_.chat_id, "nickname"]):
            nickname = bot.memory.get_by_path(['user_data', u.id_.chat_id, "nickname"])
            nickname_lower = nickname.lower()

        _normalised_full_name_upper = remove_accents(u.full_name.upper())

        if (username_lower == "all" or

                username_lower in u.full_name.replace(" ", "").lower() or
                    username_upper in _normalised_full_name_upper.replace(" ", "") or

                username_lower in u.full_name.replace(" ", "_").lower() or
                    username_upper in _normalised_full_name_upper.replace(" ", "_") or

                username_lower == nickname_lower or
                username in u.full_name.split(" ")):

            logger.info("user {} ({}) is present".format(u.full_name, u.id_.chat_id))

            if u.is_self:
                """bot cannot be @mentioned"""
                logger.debug("suppressing bot mention by {} ({})".format(event.user.full_name, event.user.id_.chat_id))
                continue

            if u.id_.chat_id == event.user.id_.chat_id and username_lower == "all":
                """prevent initiating user from receiving duplicate @all"""
                logger.debug("suppressing @all for {} ({})".format(event.user.full_name, event.user.id_.chat_id))
                continue

            if u.id_.chat_id == event.user.id_.chat_id and not noisy_mention_test:
                """prevent initiating user from mentioning themselves"""
                logger.debug("suppressing @self for {} ({})".format(event.user.full_name, event.user.id_.chat_id))
                continue

            if u.id_.chat_id in mention_chat_ids:
                """prevent most duplicate mentions (in the case of syncouts)"""
                logger.debug("suppressing duplicate mention for {} ({})".format(event.user.full_name, event.user.id_.chat_id))
                continue

            if bot.memory.exists(["donotdisturb"]):
                if _user_has_dnd(bot, u.id_.chat_id):
                    logger.info("suppressing @mention for {} ({})".format(u.full_name, u.id_.chat_id))
                    user_tracking["ignored"].append(u.full_name)
                    continue

            if username_lower == nickname_lower:
                if u not in exact_nickname_matches:
                    exact_nickname_matches.append(u)

            if (username in u.full_name.split(" ") or
                    username_upper in _normalised_full_name_upper.split(" ")):

                if u not in exact_fragment_matches:
                    exact_fragment_matches.append(u)

            if u not in mention_list:
                mention_list.append(u)

    if len(exact_nickname_matches) == 1:
        """prioritise exact nickname matches"""
        logger.info("prioritising nickname match for {}".format(exact_nickname_matches[0].full_name))
        mention_list = exact_nickname_matches
    elif len(exact_fragment_matches) == 1:
        """prioritise case-sensitive fragment matches"""
        logger.info("prioritising single case-sensitive fragment match for {}".format(exact_fragment_matches[0].full_name))
        mention_list = exact_fragment_matches
    elif len(exact_fragment_matches) > 1 and len(exact_fragment_matches) < len(mention_list):
        logger.info("prioritising multiple case-sensitive fragment match for {}".format(exact_fragment_matches[0].full_name))
        mention_list = exact_fragment_matches

    if len(mention_list) > 1 and username_lower != "all":

        send_multiple_user_message = True

        if bot.memory.exists(['user_data', event.user.id_.chat_id, "mentionmultipleusermessage"]):
            send_multiple_user_message = bot.memory.get_by_path(['user_data', event.user.id_.chat_id, "mentionmultipleusermessage"])

        if send_multiple_user_message or noisy_mention_test:
            if conv_1on1_initiator:
                text_html = _('{} users would be mentioned with "@{}"! Be more specific. List of matching users:<br />').format(
                    len(mention_list), username, conversation_name)

                for u in mention_list:
                    text_html += u.full_name
                    if bot.memory.exists(['user_data', u.id_.chat_id, "nickname"]):
                        text_html += ' (' + bot.memory.get_by_path(['user_data', u.id_.chat_id, "nickname"]) + ')'
                    text_html += '<br />'

                text_html += "<br /><em>To toggle this message on/off, use <b>/bot bemorespecific</b></em>"

                yield from bot.coro_send_message(conv_1on1_initiator, text_html)

        logger.warning("@{} not sent due to multiple recipients".format(username_lower))
        return #SHORT-CIRCUIT

    """support for reprocessor
    override the source name by defining event._external_source"""
    source_name = event.user.full_name
    if hasattr(event, '_external_source'):
        source_name = event._external_source

    """send @mention alerts"""
    for u in mention_list:
            alert_via_1on1 = True

            """pushbullet integration"""
            if bot.memory.exists(['user_data', u.id_.chat_id, "pushbullet"]):
                pushbullet_config = bot.memory.get_by_path(['user_data', u.id_.chat_id, "pushbullet"])
                if pushbullet_config is not None:
                    if pushbullet_config["api"] is not None:
                        success = False
                        try:
                            pb = PushBullet(pushbullet_config["api"])
                            push = pb.push_link(
                                title = _("{} mentioned you in {}").format(source_name, conversation_name),
                                    body=event.text,
                                    url='https://hangouts.google.com/chat/{}'.format(event.conv.id_) )
                            if isinstance(push, tuple):
                                # backward-compatibility for pushbullet library < 0.8.0
                                success = push[0]
                            elif isinstance(push, dict):
                                success = True
                            else:
                                raise TypeError("unknown return from pushbullet library: {}".format(push))
                        except Exception as e:
                            logger.exception("pushbullet error")

                        if success:
                            user_tracking["mentioned"].append(u.full_name)
                            logger.info("{} ({}) alerted via pushbullet".format(u.full_name, u.id_.chat_id))
                            alert_via_1on1 = False # disable 1on1 alert
                        else:
                            user_tracking["failed"]["pushbullet"].append(u.full_name)
                            logger.warning("pushbullet alert failed for {} ({})".format(u.full_name, u.id_.chat_id))

            if alert_via_1on1:
                """send alert with 1on1 conversation"""
                conv_1on1 = yield from bot.get_1to1(u.id_.chat_id, context={ 'initiator_convid': event.conv_id })
                if username_lower == "all":
                    message_mentioned = _("<b>{}</b> @mentioned ALL in <i>{}</i>:<br />{}")
                else:
                    message_mentioned = _("<b>{}</b> @mentioned you in <i>{}</i>:<br />{}")
                if conv_1on1:
                    yield from bot.coro_send_message(
                        conv_1on1,
                        message_mentioned.format(
                            source_name,
                            conversation_name,
                            event.text)) # prevent internal parser from removing <tags>
                    mention_chat_ids.append(u.id_.chat_id)
                    user_tracking["mentioned"].append(u.full_name)
                    logger.info("{} ({}) alerted via 1on1 ({})".format(u.full_name, u.id_.chat_id, conv_1on1.id_))
                else:
                    user_tracking["failed"]["one2one"].append(u.full_name)
                    if bot.get_config_suboption(event.conv_id, 'mentionerrors'):
                        yield from bot.coro_send_message(
                            event.conv,
                            _("@mention didn't work for <b>{}</b>. User must say something to me first.").format(
                                u.full_name))
                    logger.warning("user {} ({}) could not be alerted via 1on1".format(u.full_name, u.id_.chat_id))

    if noisy_mention_test:
        text_html = _("<b>@mentions:</b><br />")
        if len(user_tracking["failed"]["one2one"]) > 0:
            text_html = text_html + _("1-to-1 fail: <i>{}</i><br />").format(", ".join(user_tracking["failed"]["one2one"]))
        if len(user_tracking["failed"]["pushbullet"]) > 0:
            text_html = text_html + _("PushBullet fail: <i>{}</i><br />").format(", ".join(user_tracking["failed"]["pushbullet"]))
        if len(user_tracking["ignored"]) > 0:
            text_html = text_html + _("Ignored (DND): <i>{}</i><br />").format(", ".join(user_tracking["ignored"]))
        if len(user_tracking["mentioned"]) > 0:
            text_html = text_html + _("Alerted: <i>{}</i><br />").format(", ".join(user_tracking["mentioned"]))
        else:
            text_html = text_html + _("Nobody was successfully @mentioned ;-(<br />")

        if len(user_tracking["failed"]["one2one"]) > 0:
            text_html = text_html + _("Users failing 1-to-1 need to say something to me privately first.<br />")

        yield from bot.coro_send_message(event.conv, text_html)

def pushbulletapi(bot, event, *args):
    """allow users to configure pushbullet integration with api key
        /bot pushbulletapi [<api key>|false, 0, -1]"""

    # XXX: /bot config exposes all configured api keys (security risk!)

    if len(args) == 1:
        value = args[0]
        if value.lower() in ('false', '0', '-1'):
            value = None
            yield from bot.coro_send_message(
                event.conv,
                _("deactivating pushbullet integration"))
        else:
            yield from bot.coro_send_message(
                event.conv,
                _("setting pushbullet api key"))

        bot.initialise_memory(event.user.id_.chat_id, "user_data")
        bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "pushbullet"], { "api": value })
        bot.memory.save()
    else:
        yield from bot.coro_send_message(
            event.conv,
            _("pushbullet configuration not changed"))


def bemorespecific(bot, event, *args):
    """toggle the "be more specific message" on and off permanently"""
    bot.initialise_memory(event.user.id_.chat_id, "user_data")
    if bot.memory.exists(['user_data', event.user.id_.chat_id, "mentionmultipleusermessage"]):
        _toggle = bot.memory.get_by_path(['user_data', event.user.id_.chat_id, "mentionmultipleusermessage"])
        _toggle = not _toggle
    else:
        _toggle = False
    bot.memory.set_by_path(['user_data', event.user.id_.chat_id, "mentionmultipleusermessage"], _toggle)
    bot.memory.save();
    if _toggle:
        yield from bot.coro_send_message(
            event.conv,
            _('<em>"be more specific" for mentions toggled ON</em>'))
    else:
        yield from bot.coro_send_message(
            event.conv,
            _('<em>"be more specific" for mentions toggled OFF</em>'))


def setnickname(bot, event, *args):
    """allow users to set a nickname for sync relay
        /bot setnickname <nickname>"""

    truncatelength = 16 # What should the maximum length of the nickname be?
    minlength = 2 # What should the minimum length of the nickname be?

    nickname = ' '.join(args).strip()

    # Strip all non-alphanumeric characters
    nickname = re.sub('[^0-9a-zA-Z-_]+', '', nickname)

    # Truncate nickname
    nickname = nickname[0:truncatelength]

    if len(nickname) < minlength and not nickname == '': # Check minimum length
        yield from bot.coro_send_message(event.conv, _("Error: Minimum length of nickname is {} characters. Only alphabetical and numeric characters allowed.").format(minlength))
        return

    # perform hard-coded substitution on words that trigger easter eggs
    #   dammit google! ;P
    substitution = {
        "woot": "w00t",
        "woohoo": "w00h00",
        "lmao": "lma0",
        "rofl": "r0fl",

        "hahahaha": "ha_ha_ha_ha",
        "hehehehe": "he_he_he_he",
        "jejejeje": "je_je_je_je",
        "rsrsrsrs": "rs_rs_rs_rs",

        "happy birthday": "happy_birthday",
        "happy new year": "happy_new_year",

        "xd": "x_d"
    }
    for original in substitution:
        if original in nickname.lower():
            pattern = re.compile(original, re.IGNORECASE)
            nickname = pattern.sub(substitution[original], nickname)

    # Prevent duplicate nicknames
    # First, populate list of nicks if not already
    if not nicks:
        for userchatid in bot.memory.get_option("user_data"):
            usernick = bot.memory.get_suboption("user_data", userchatid, "nickname")
            if usernick:
                nicks[userchatid] = usernick.lower()

    # is the user trying to re-set his own nickname? - don't do anything if that is the case
    if event.user.id_.chat_id in nicks:
        if nickname.lower() == nicks[event.user.id_.chat_id].lower():
            actual_nickname = bot.memory.get_suboption("user_data", event.user.id_.chat_id, "nickname")
            yield from bot.coro_send_message(event.conv, _('<i>Your nickname is already <b>`{}`</b></i>').format(actual_nickname))
            return

    # check whether another user has the same nickname
    if nickname.lower() in nicks.values():
        yield from bot.coro_send_message(event.conv, _('<i>Nickname <b>`{}`</b> is already in use by another user').format(nickname))
        return

    bot.initialise_memory(event.user.id_.chat_id, "user_data")

    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "nickname"], nickname)

    # Update nicks cache with new nickname
    nicks[event.user.id_.chat_id] = nickname

    try:
        label = '{0} ({1})'.format(event.user.full_name.split(' ', 1)[0], nickname)
    except TypeError:
        label = event.user.full_name
    bot.memory.set_by_path(["user_data", event.user.id_.chat_id, "label"], label)

    bot.memory.save()

    if(nickname == ''):
        yield from bot.coro_send_message(event.conv, _("Removing nickname"))
    else:
        yield from bot.coro_send_message(
            event.conv,
            _("Setting nickname to '{}'").format(nickname))
