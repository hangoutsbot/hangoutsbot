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
                  "hangout": "<hangout-id>",
                  "channel": ["<team-name>", "<channel-id>"]
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
        try:
            # Fetch v3 syncs from plugin data.
            migrate = bot.memory.get_by_path(["slackrtm", team["name"], "synced_conversations"])
            logger.debug("Found {} sync(s) in v3 config for '{}' to migrate".format(len(migrate), team["name"]))
        except (KeyError, TypeError):
            # Fetch v2 syncs from user data, if v3 data doesn't exist.
            migrate = bot.user_memory_get(team["name"], "synced_conversations")
            if migrate is None:
                migrate = []
                logger.warn("No syncs for '{}' found in either v2 or v3 config".format(team["name"]))
            else:
                logger.debug("Found {} sync(s) in v2 config for '{}' to migrate".format(len(migrate), team["name"]))
        # Convert all syncs to the new config format.
        for sync in migrate:
            syncs.append({"hangout": sync["hangoutid"],
                          "channel": [team["name"], sync["channelid"]]})
    # Write a backup of the old config, then save the new config.
    logger.debug("Writing new config")
    bot.config.set_by_path(["slackrtm [legacy backup]"], config)
    bot.config.set_by_path(["slackrtm"], {"teams": teams, "syncs": syncs})
    bot.config.save()
