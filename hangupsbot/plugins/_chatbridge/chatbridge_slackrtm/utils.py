import logging


logger = logging.getLogger(__name__)


def convert_legacy_config(bot):
    """
    Old config structure:

        {
          "slackrtm": [
            {
              "name": "<team-name>",
              "key": "<token>",
              "admins": [...]
            }
          ]
        }

    Old memory structure:

        {
          // SlackRTM in v2
          "user_data": {
            "<team-name>": {
              "synced_conversations": [
                {
                  "channelid": "<channel-id>",
                  "hangoutid": "<hangout-id>",
                  ...
                }
              ]
            }
          },
          // SlackRTM in v3
          "slackrtm": {
            "<team-name>": {
              "identities": {...},
              "synced_conversations": [
                {
                  "channelid": "<channel-id>",
                  "hangoutid": "<hangout-id>",
                  ...
                }
              ]
            }
          }
        }

    New config structure:

        {
          "slackrtm": {
            "<team-name>": {
              "token": "<token>",
              "admins": [...],
              "syncs": [
                {
                  "hangouts": ["<hangout-id>", ...],
                  "slack": [["<team-name>", "<channel-id>"], ...]
                }
              ]
            }
          }
        }

    Identities stay in memory, syncs move to config.
    """
    # SlackRTM in v3 uses "slackrtm" under config for both teams and syncs.
    # This plugin uses a dict structure, so rewrite any existing config.
    config = bot.get_config_option("slackrtm")
    if isinstance(config, dict):
        # Config is in the new format already.
        return
    logger.info("Legacy config detected, running migration")
    teams = {}
    syncs = []
    for team in config:
        logger.debug("Migrating team '{}'".format(team["name"]))
        teams[team["name"]] = {"token": team["key"], "admins": team["admins"]}
        # Fetch v2 syncs from user data.
        migrate = bot.user_memory_get(team["name"], "synced_conversations") or []
        # Fetch v3 syncs from plugin data.
        try:
            migrate += bot.memory.get_by_path(["slackrtm", team["name"], "synced_conversations"])
        except KeyError:
            continue
        # Convert all syncs to the new config format.
        logger.debug("Found {} sync(s) for '{}' to migrate".format(len(migrate), team["name"]))
        for sync in migrate:
            syncs.append({"hangouts": [sync["hangoutid"]],
                          "slack": [[team["name"], sync["channelid"]]]})
    # Write a backup of the old config, then save the new config.
    logger.debug("Writing new config")
    bot.config.set_by_path(["slackrtm [legacy backup]"], config)
    bot.config.set_by_path(["slackrtm"], {"teams": teams, "syncs": syncs})
    bot.config.save()
