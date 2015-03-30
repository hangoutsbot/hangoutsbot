# Introduction

Hangupsbot is a bot designed for working with Google Hangouts.
* **Mentions** :
  If somebody mentions you in a room, receive a private hangout from the bot with details onthe mention, 
  including context, room and person who mentioned you.
* **Syncouts** : 
  A syncout is two Hangout group chats that have their messages forwarded to each other, allowing seamless 
  interaction between the two rooms. Primarily used to beat the 150-member chat limit, but it can also be
  used for temporarily connecting teams together to interact.
* [**Hubot Integration**](https://github.com/nylonee/hangupsbot/wiki/Hubot-Integration) :
  Hangupsbot allows you to connect to [Hubot](https://hubot.github.com/), instantly providing you access 
  to hundreds of developed chat tools and plugins.
* **Lookups** :
  Google Sheets can be attached to the bot, which allows you to look up data in the 
  spreadsheet instantly with just a few keywords.
* **Pushbullet API** :
  [Pushbullet](https://www.pushbullet.com/) support for mentions is available.
* **Plugins, sinks and hooks** : 
  The bot has [instructions for developing your own plugins, sinks and hooks]
  (https://github.com/nylonee/hangupsbot/wiki/Authoring-Bot-Extensions), allowing the bot to interact 
  with external services such as your company website, Google APIs and much more.
* **Plugin mania** : 
  eastereggs, games, nickname support - **[the list goes on]
    (https://github.com/nylonee/hangupsbot/wiki/Plugin-List)**!

# IMPORTANT

This is a [fork](https://gitlab.sabah.io/eol/mogunsamang) of a [fork](https://github.com/xmikos/hangupsbot).

* To execute: `python3 hangupsbot.py`
* Any current tests will be in `<path of hangupsbot.py>/tests/`
* Please see the original documentation which is reproduced below
  (after the TODO section)

# General Configuration for Administrators

Configuration directives can be specified in `config.json`.

Most configuration directives are specified **globally** 
* Global directives are always specified in the "root" of `config.json`.
* To specify a per-conversation directive, the same configuration option should
  be defined as `config.conversations[<conversation-id>].<configuration option>`.
* Per-conversation directives override global settings, if both are set.
* Manually-configured per-conversation directives are DEPRECATED.

## Plugins

The `plugins` key in `config.json` allows you to optionally specify a list of plugins
  that will be loaded by the bot on startup. If this option is left as `null`, then
  all available plugins will be loaded.

To specify the plugins to be loaded, first ensure that the correct `.py` files are 
  inside your `hangupsbot/plugin/` directory, then modify the `plugins` key in
  `config.json` to reflect which plugins/files you want to load e.g.
    `plugins: ["mentions", "default", "chance", "syncrooms"]`

Some plugins may require extra configuration as documented in this README. 
  `config.json` is the the configuration provider for the bot and its plugins.

Some interesting plugins:
* [mentions plugin]
  (https://github.com/nylonee/hangupsbot/wiki/Mentions-Plugin)
  * alert users when their names are mentioned in a chat
* [subscribe plugin]
  (https://github.com/nylonee/hangupsbot/wiki/Subscribe-Plugin)
  * alert users when keywords they are subscribed to are said in a chat 
* [syncout / syncrooms plugins]
  (https://github.com/nylonee/hangupsbot/wiki/Syncouts-Plugin)
  * relay chat messages between different hangout group conversations (syncrooms)
  * configure via bot commands (syncrooms_config)
  * automated translation via Google Translate of relayed messages (syncrooms_autotranslate)

The wiki has a more comprehensive **[list of plugins]
  (https://github.com/nylonee/hangupsbot/wiki/Plugin-List)**...

# Interacting with the Bot

There are three general types of interactions with the bot:
* **`/bot` commands** begin with `/bot` e.g. `/bot dosomething`
  * some bot commands are admin-only
* **`/me` triggers** begin with `/me` and frequently form a complete sentence e.g.
  `/me rolls a dice`
  * these kind of triggers are generally accessible to all users
* custom interactions (usage and acessibility varies by plugin)

**Without any plugins**, the bot only recognises the following two `/bot` commands:

`/bot help`
* Bot lists all supported commands in a private message with the user
* If the user does not have a 1-on-1 channel open, it will publicly tell 
  the user to PM the bot and say hi.

`/bot ping`
* Bot replies with a `pong`.

Please see the wiki for the **[list of plugins]
  (https://github.com/nylonee/hangupsbot/wiki/Plugin-List)** to find out more
  about each plugin and their usage.

# Debugging

* Run the bot with the `-d` parameter e.g. `python3 hangupsbot.py -d` - this
  lowers the log level to `INFO` for a more verbose and informative log file.
* `tail` the log file, which is probably located at
  `/<user>/.local/share/hangupsbot/hangupsbot.log` - the location varies by
  distro!
* Console output (STDOUT) is fairly limited whatever the log level, so rely
  on the output of the log file instead.

# Extending

Please see https://github.com/nylonee/hangupsbot/wiki/Authoring-Bot-Extensions

---

HangupsBot (original README.md)
===============================

Bot for Google Hangouts

Requirements
------------

- Python >= 3.3
- hangups (https://github.com/tdryer/hangups)
- appdirs (https://github.com/ActiveState/appdirs)
- asyncio (https://pypi.python.org/pypi/asyncio) for Python < 3.4
- BeautifulSoup4

Usage
-----

Run `hangupsbot --help` to see all available options.
Start HangupsBot by running `hangupsbot`.

You can configure basic settings in `config.json` file. This file will be
copied to user data directory (e.g. `~/.local/share/hangupsbot/` on Linux)
after first start of HangupsBot.

The first time you start HangupsBot, you will be prompted to log into your
Google account. Your credentials will only be sent to Google, and only
session cookies will be stored locally. If you have trouble logging in,
try logging in through a browser first.

Help
----

    usage: hangupsbot [-h] [-d] [--log LOG] [--cookies COOKIES] [--config CONFIG]

    optional arguments:
      -h, --help         show this help message and exit
      -d, --debug        log detailed debugging messages (default: False)
      --log LOG          log file path (default:
                         ~/.local/share/hangupsbot/hangupsbot.log)
      --cookies COOKIES  cookie storage path (default:
                         ~/.local/share/hangupsbot/cookies.json)
      --config CONFIG    config storage path (default:
                         ~/.local/share/hangupsbot/config.json)

