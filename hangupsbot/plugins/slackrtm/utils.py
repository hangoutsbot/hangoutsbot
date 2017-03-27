import logging


logger = logging.getLogger(__name__)


_slackrtms = []

def _slackrtm_conversations_set(bot, team_name, synced_hangouts):
    memory_root_key = "slackrtm"

    if not bot.memory.exists([ memory_root_key ]):
        bot.memory.set_by_path([ memory_root_key ], {})

    if not bot.memory.exists([ memory_root_key, team_name ]):
        bot.memory.set_by_path([ memory_root_key, team_name ], {})

    bot.memory.set_by_path([ memory_root_key, team_name, "synced_conversations" ], synced_hangouts)
    bot.memory.save()

def _slackrtm_conversations_get(bot, team_name):
    memory_root_key = "slackrtm"
    synced_conversations = False
    if bot.memory.exists([ memory_root_key ]):
        full_path = [ memory_root_key, team_name, "synced_conversations" ]
        if bot.memory.exists(full_path):
            synced_conversations = bot.memory.get_by_path(full_path) or False
    else:
        # XXX: older versions of this plugin incorrectly uses "user_data" key
        logger.warning("using broken legacy memory of synced conversations")
        synced_conversations = bot.user_memory_get(team_name, 'synced_conversations')
    return synced_conversations

def _slackrtm_link_profiles(hangoutsbot, hangouts_uid, slack_teamname, slack_uid, base_key, remove):
    memory_path = ["slackrtm", slack_teamname, "identities"]

    mapped_identities = { "slack": {}, "hangouts": {} }
    if hangoutsbot.memory.exists(memory_path):
        mapped_identities = hangoutsbot.memory.get_by_path(memory_path)

    if base_key == "hangouts":
        uid1 = hangouts_uid
        uid2 = slack_uid
        link_key = "slack"
    elif base_key == "slack":
        uid2 = hangouts_uid
        uid1 = slack_uid
        link_key = "hangouts"
    else:
        raise ValueError("unknown base key")

    if uid1 in mapped_identities[base_key]:
        existing_uid2 = mapped_identities[base_key][uid1]
        if( existing_uid2 != uid2
            and ( existing_uid2 in mapped_identities[link_key]
                  and mapped_identities[link_key][existing_uid2] == uid1 )):
            return "profile already synced to another user, please contact bot administrator"

        if not remove:
            return "mapping already exist, call command with \"remove\" appended to delink"

        del mapped_identities[base_key][uid1]
        if existing_uid2 in mapped_identities[link_key]:
            del mapped_identities[link_key][existing_uid2]
        message = "mapping was removed"

    else:
        mapped_identities[base_key][uid1] = uid2
        logger.info("{} {} to {} {}, slack team = {}".format(base_key, uid1, link_key, uid2, slack_teamname))

        # a user must be mapped on slack->ho AND ho->slack to be valid
        if( uid2 not in mapped_identities[link_key]
                or mapped_identities[link_key][uid2] != uid1 ):
            message = "use the equivalent identify command in {} to complete the mapping".format(link_key)
        else:
            message = "mapping is complete"

    hangoutsbot.memory.set_by_path(memory_path, mapped_identities)
    hangoutsbot.memory.save()

    return message
