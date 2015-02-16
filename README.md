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
  eastereggs, games, nickname support - the list goes on!

# IMPORTANT

This is a [fork](https://gitlab.sabah.io/eol/mogunsamang) of a [fork](https://github.com/xmikos/hangupsbot).

* To execute: `python3 hangupsbot.py`
* Any current tests will be in `<path of hangupsbot.py>/tests/`
* Please see the original documentation which is reproduced below
  (after the TODO section)

# Installation

Install python 3.4 from source

```
wget https://www.python.org/ftp/python/3.4.2/Python-3.4.2.tgz
tar xvf Python-3.4.2.tgz
cd Python-3.4.2
./config
make
make install
```

Install dependencies

```
pip3 install -r requirements.txt
```

# Users: Quickstart

If the mentions plugin is available, please see:
  https://github.com/nylonee/hangupsbot/wiki/Mentions-Plugin#users-quickstart

## Usage of @mentions

Documentation has been moved to the wiki @ [Mentions Plugin]
  (https://github.com/nylonee/hangupsbot/wiki/Mentions-Plugin)

# Admins: Quick Installation & Configuration

* `config.json` is found in two places:
  * one folder below `hangupsbot.py`;and later,
  * ...in `/root/.local/share/hangupsbot/` after first successful run
* add (or replace) your *user id* into the `admins` array in config.json

```
{
  "admins": [
    "104821221116551390464"
  ],
  "autoreplies": [
  ...
```
To find out how to get your user id, read on!

## Getting your User ID

### first time admins with no existing bot

Requires plugin: [**default**]
  (https://github.com/nylonee/hangupsbot/blob/master/hangupsbot/plugins/default.py)

1. start the bot with a valid gmail account (not your actual account!)
2. open a hangout with the bot (using your actual account), say anything to it
3. login into the bot's gmail account and ensure chat is activated
4. open up invites, and accept your incoming invite (from your actual account)
5. restart the bot and it will dump out a conversation and users list
6. find your actual account user name, the chat_id will be listed next to it

### with an existing bot

Requires plugin: [**default**]
  (https://github.com/nylonee/hangupsbot/blob/master/hangupsbot/plugins/default.py)

join a group with an existing bot and issue this command `/bot whoami`, your
chat_id will be displayed

# Admins: General Configuration

Configuration directives can be specified in `config.json`.

Most configuration directives are specified **globally** 
* Global directives are always specified in the "root" of `config.json`.
* To specify a per-conversation directive, the same configuration option should
  be defined as `config.conversations[<conversation-id>].<configuration option>`.
* Per-conversation directives override global settings, if both are set.
* Manually-configured per-conversation directives are DEPRECATED.

## Admins: Configuring Plugins

The `plugins` key in `config.json` allows you to optionally specify a list of plugins
  that will be loaded by the bot on startup. If this option is left as `null`, then
  all available plugins will be loaded.

To specify the plugins to be loaded, first ensure that the correct `.py` files are 
  inside your `hangupsbot/plugin/` directory, then modify the `plugins` key in
  `config.json` to reflect which plugins/files you want to load e.g.
    `plugins: ["mentions", "default", "chance", "syncrooms"]`

Some plugins may require extra configuration as documented in this README. 
  `config.json` is the the configuration provider for the bot and its plugins.

## Admins: @mentions Configuration

Documentation has been moved to the wiki @ [Mentions Plugin]
  (https://github.com/nylonee/hangupsbot/wiki/Mentions-Plugin)

## Admins: Syncing Chats with Syncout / Syncrooms

The syncouts/syncrooms family of plugins include:
* Relaying chat messages between different hangout group conversations (syncrooms)
* Configuring syncouts via bot commands (syncrooms_config)
* Automatic translation via Google Translate of relayed messages (syncrooms_autotranslate)

Documentation has been moved to the wiki @ [Syncouts Plugin]
  (https://github.com/nylonee/hangupsbot/wiki/Syncouts-Plugin)

# User Triggers (`/me` prefix)

Plugins that implement `/me` triggers:

* [chance](https://github.com/nylonee/hangupsbot/wiki/Chance-Plugin)
  users can roll a dice and flip coins
* [lottery](https://github.com/nylonee/hangupsbot/wiki/Lottery-Plugin)
  users can draw from a randomised list of "things" from admin-setup "lotteries"  

# Bot Commands

All bot commands must be prefixed by `/bot`, as in `/bot <command>`.

## Administrative Commands

Plugins which implement administrative commands:
* [default](https://github.com/nylonee/hangupsbot/wiki/Default-Commands-Plugin)
  standard set of commands useful for bot management
* [namelock](https://github.com/nylonee/hangupsbot/wiki/Namelock-Plugin)
  allows admins to lock the title of a conversation
* [easteregg](https://github.com/nylonee/hangupsbot/wiki/Hangouts-Easter-eggs-Plugin)
  delight (annoy) users with ponies and pitchforks!
* [lottery](https://github.com/nylonee/hangupsbot/wiki/Lottery-Plugin)
  admins can prepare lotteries for users to draw from   

## User Commands

These are commands that can be executed by any user, based on the default
configuration in `config.commands_admin`.

`help`
* Bot lists all supported commands in a private message with the user
* If the user does not have a 1-on-1 channel open, it will publicly tell 
  the user to PM the bot and say hi.

`ping`
* Bot replies with a `pong`.

Plugins which implement user commands:
* [default](https://github.com/nylonee/hangupsbot/wiki/Default-Commands-Plugin)
  standard set of commands useful for bot testing
* [mentions](https://github.com/nylonee/hangupsbot/wiki/Mentions-Plugin)
  set pushbullet api key, do-not-disturb status and test mentions
* [lookup](https://github.com/nylonee/hangupsbot/wiki/Lookup-Plugin)
  lookup an entry in a linked google spreadsheet
* [subscribe](https://github.com/nylonee/hangupsbot/wiki/Subscribe-Plugin)
  be alerted when certain words are said inside a chat

# Developers: Debugging

* Run the bot with the `-d` parameter e.g. `python3 hangupsbot.py -d` - this
  lowers the log level to `INFO` for a more verbose and informative log file.
* `tail` the log file, which is probably located at
  `/<user>/.local/share/hangupsbot/hangupsbot.log` - the location varies by
  distro!
* Console output (STDOUT) is fairly limited whatever the log level, so rely
  on the output of the log file instead.

# Developers: Extending the Bot

Please see https://github.com/nylonee/hangupsbot/wiki/Authoring-Bot-Extensions

# Developers: TODO

* run as service
  * alternatively [cron](http://www.raspberrypi-spy.co.uk/2013/07/running-a-python-script-at-boot-using-cron/)
    and a [bash script](https://gist.github.com/endofline/34fc36cfbd149bcc7d15) works great too!

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
