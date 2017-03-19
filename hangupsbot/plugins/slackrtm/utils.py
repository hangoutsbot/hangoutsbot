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
