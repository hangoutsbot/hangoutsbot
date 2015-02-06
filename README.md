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

1. You need to open a 1-on-1 conversation with the bot first and say "hello"
   (or anything!)
2. Then give yourself a @mention in another HO where the bot is participating
   as a group member

This procedure is necessary to let the bot know you're alive ;P
No seriously, the above steps are **required** to authorise two-way
communication between the bot and your own account.

## Usage of @mentions

Some general rules:
* If `mentionquidproquo` is ON, only users who have already said something to
  the bot in private will be able to @mention others.
* If a @mention matches multiple users, the bot will privately warn the user
  that too many users were selected. A list of all matching users will be
  provided as a guide to the user.
* A @mention must be at least 3 characters or longer (not counting the `@`)

A @mention matches the following:
* A part of the combined first name and last name of the user
  e.g. `@abc` matches `AB Chin` (bot sees `abchin`)
* A part of the combined first name and last name with spaces replaced by
  the underscore
  e.g. `@ab_c` matches `AB Chin` (bot sees `AB_Chin`)
* An exact match with a user nickname, if the user has previously has
  previously `/bot set nickname abc`
  e.g. `@abc` matches nickname `abc` but NOT nicknames `abcd` or `zabc`

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

## Getting Your User ID

### first time admins with no existing bot

1. start the bot with a valid gmail account (not your actual account!)
2. open a hangout with the bot (using your actual account), say anything to it
3. login into the bot's gmail account and ensure chat is activated
4. open up invites, and accept your incoming invite (from your actual account)
5. restart the bot and it will dump out a conversation and users list
6. find your actual account user name, the chat_id will be listed next to it

### with an existing bot

join a group with an existing bot and issue this command `/bot whoami`, your
chat_id will be displayed

# Admins: Configuration

Configuration directives can be specified in `config.json`.

Most configuration directives can be specified **globally** or **per-conversation**.
* Global directives are always specified in the "root" of `config.json`.
* To specify a per-conversation directive, the same configuration option should
  be defined as `config.conversations[<conversation-id>].<configuration option>`.
* Per-conversation directives override global settings, if both are set.

## Mentions

`mentionquidproquo`
* default: `true`
* only users who have already initiated a 1-on-1 dialog with the bot will be
  able to use @mentions and alert other users

`mentionerrors`
* default: `false`
* outputs any problems with a @mention to the current conversation
* verbose output and should only be used for debugging
* alternative is to use `/bot mention <name-fragment> test`
  (see bot command below)

`mentionall`
* default: `true`
* enables/disables @all for mentions
* when set to `false`, admins and chat ids listed in `mentionallwhitelist`
  can still use **@all**
* users who are blocked from using @mentions (`mentionall == false`;
  not an admin; not whitelisted) will be notified privately if the bot
  already has a 1-on-1 with them

`mentionallwhitelist`
* default: `[]`
* allow listed chat_ids to use @all in mentions regardless of
  global/per-conversation `mentionall` setting

# Syncing Chats (Syncout / Syncrooms)

Requires plugin: [**syncrooms**](https://github.com/nylonee/hangupsbot/blob/master/hangupsbot/plugins/syncrooms.py)

Chats can be synced together, called a 'syncout'. If a person says something in chat A, that message will be relayed into chat B by the bot, and vice versa, allowing multiple rooms to have conversations with each other. The primary use for this is to have more than 150 (the hangout limit) users talking to each other in the same room.

Syncouts/syncrooms only has two `config.json` keys, documented in the following section:

`syncing_enabled`
* default: `not set`
* If `true`, will look for `config.sync_rooms` and start relaying chats across configured rooms
* Can only be enabled/disabled globally

```
"sync_rooms": [
  [
      "CONVERSATION_1_ID",
      "CONVERSATION_2_ID"
  ],
  [
      "CONVERSATION_3_ID",
      "CONVERSATION_4_ID",
      "CONVERSATION_5_ID"
  ]
]
```
* a list containing another set of lists, which contains conversation IDs to sync, this allows
  the bot to support multiple separately-synced chats e.g. rooms A, B, C and D, E separately.

## Special note for legacy syncouts configuration

Older bots would be configured using the legacy syncout configuration. The plugin will 
**automatically migrate** these old configurations to the new format by rewriting your
`config.json` file. Other keys in `config.conversations` will not be affected by the 
migration to preserve compatibility with older features.

The legacy configuration is provided here for reference purposes - it may be removed in
the future:
```
"conversations":
{
  "CONVERSATION_1_ID": {  
    "sync_rooms": ["CONVERSATION_1_ID", "CONVERSATION_2_ID"]  
  },  
  "CONVERSATION_2_ID": {  
    "sync_rooms": ["CONVERSATION_1_ID", "CONVERSATION_2_ID"]
  },  
  "CONVERSATION_3_ID": {  
    "sync_rooms": ["CONVERSATION_3_ID", "CONVERSATION_4_ID", "CONVERSATION_5_ID"]  
  },
  "CONVERSATION_4_ID": {  
    "sync_rooms": ["CONVERSATION_3_ID", "CONVERSATION_4_ID", "CONVERSATION_5_ID"]  
  },
  "CONVERSATION_5_ID": {  
    "sync_rooms": ["CONVERSATION_3_ID", "CONVERSATION_4_ID", "CONVERSATION_5_ID"]  
  }
}
```

# User Triggers (`/me` prefix)

Special `/me` triggers are available when the [**chance** plugin]
(https://github.com/nylonee/hangupsbot/blob/master/hangupsbot/plugins/chance.py) is loaded.
All these must be prefixed by `/me`, as in `/me <trigger>`.

`roll[s] [a] dice`
* Bot will (virtually) roll a dice and return the number **1-6**

`flip[s] [a] coin`
* Bot will (virtually) flip a coin and return **heads** or **tails**.

`draw[s] [a|an] <thing>`
* Bot will get a random <thing> from a box.
* The box must be "prepared" first (see Bot Commands below).
* Used for user lotteries
* `draw`-ing without a `<thing>` will always fetch an item from the
  **default** lottery/box (if its prepared). To draw from another box,
  `<thing>` must be supplied.
* Bot keeps tracks of people who have already participated in the draw.
  * Trying to draw again will make the bot remind you of your previous results.
  * WARNING: Records are not persisted between bot restarts!

# Bot Commands

All bot commands must be prefixed by `/bot`, as in `/bot <command>`.

## Administrative Commands

These are commands that can only be executed by admins, based on the default
configuration in `config.commands_admin`.

`users`
* Bot lists all users in current conversation.
* List will contain user G+ profile link and email (if available).

`user <string name>`
* Bot searches for users whose names contain `<string name>` in internal user list.
* Spaces are not allowed.
* The bot will search all users in all participating conversations.

`hangouts`
* Bot lists all participating conversations with additional details.
* Legend: `c` = commands enabled; `f` = forwarding enabled; `a` = auto-replies.

`rename <string title>`
* Bot renames the current conversation.
* Spaces in the title are allowed.
* Works with both 1-on-1 or group conversations.
* Note: 1-on-1 renames may not reflect their title properly on desktop clients.

`topic <string title>`
* Works like `rename`
* Will change the topic back to `<string title>` if anybody attempts to change it

`leave [<conversation id>]`
* Bot leaves the current hangout if `<conversation id>` not specified.

`easteregg <ponies|pitchforks|bikeshed|shydino> <number> <period>`
* Bot activates Hangouts easter-egg animation (varies by client).
* `<number>` is the amount of repetition with delay of `<period>` in seconds.

`quit`
* Kills the running bot process on the server with a disconnection.

`config get <key> [<subkey> [...]]`
* Bot reads config.json and displays contents of `config.<key>[.<subkey>...]`

`config set <key> [<subkey> [...]] "<value>"`
* Bot sets contents of `config.<key>[.<subkey>...]` to `<value>`
* `<value>` must be enclosed in double-quotes and is interpreted as JSON.
* Changes are saved instantly into `config.json`.
* WARNING: This command is low-level and can scramble the configuration.
* DEVELOPERS: This command is **DEPRECATED**

`config append <key> [<subkey> [...]] "<value>"`
* Bot appends <value> to list at `config.<key>[.<subkey>...]`
* `<value>` must be enclosed in double-quotes and is interpreted as JSON.
* Only works if the key pointed at is an actual list.
* Usually used to add administrator ids to `config.admins`
* WARNING: This command is low-level and can scramble the configuration.
* DEVELOPERS: This command is **DEPRECATED**

`config remove <key> [<subkey> [...]] "<value>"`
* Bot removes specified <value> from list at `config.<key>[.<subkey>...]`
* `<value>` must be enclosed in double-quotes and is interpreted as JSON.
* Only works if the key pointed at is an actual list.
* Usually used to remove administrator ids from `config.admins`
* WARNING: This command is low-level and can scramble the configuration.
* DEVELOPERS: This command is **DEPRECATED**

## Standard Commands

These are commands that can be executed by any user, based on the default
configuration in `config.commands_admin`.

`help`
* Bot lists all supported commands in a private message with the user
* If the user does not have a 1-on-1 channel open, it will publicly tell 
  the user to PM the bot and say hi.

`ping`
* Bot replies with a `pong`.

`echo <string anything>`
* Bot replies with `<string anything>` as the message.
* Spaces are allowed.

`pushbulletapi <apikey|false|0|-1>`
* Sets/unsets the pushbullet api key for current user.
* When user is @mentioned, bot will alert user through PushBullet.
* If the push fails, bot will revert to normal hangouts-based alert.
* `false`, `0` or `-1` Disables pushbullet integration for current user.

`dnd`
* Toggles global DND (Do Not Disturb) for current user.
* Bot will message user whether DND is toggled on or off.
* User will not receive alerts for @mentions.

`setnickname <nickname>`
* Bot sets the nickname for the current user
* `/whoami` will return the current nickname
* Call it again to re-set the `<nickname>` as preferred

`whoami`
* Bot replies with the current user information:
  * first name, nickname and `chat_id`, OR
  * full name and `chat_id`

`whereami`
* Bot replies with the conversation name and `conversation id`.

`mention <name fragment> [test]`
* Alias for @<name fragment>.
* Triggers the same mechanism for @mentions.
* `<name fragment>` cannot contain spaces.
* Adding optional second parameter `test` will show additional log information
  inside the current conversation when attempting to alert users. This
  can be used to check for any @mention errors with specific users.

`lookup <keyword>`
* Used in conjunction with a published Google Spreadsheet
* Need to enable in config: `spreadsheet_enabled`, `spreadsheet_url` and
  `spreadsheet_table_class`
* Will look up each row of a spreadsheet and if the keyword is found will
  return the whole row

`prepare [<things>] <listdef>`
* Bot prepares a list of `<things>` and puts them in a virtual box for lottery
  drawings.
  * If `<things>` is not supplied, then "default" will be used.
  * WARNING: Records are not persisted between bot restarts!
* `<listdef>` can be:
  * comma-separated list of values (no spaces!) e.g. `abc,ghi,xyz`
  * range of numbers e.g. 50-100
  * "numberTokens" e.g. 9long1short
* Each user must issue `/me draws` (or similar) to get a random item from the
  box. Note: `/me draw` always draws from "default" if available; to draw from
  another box, `/me draw [a|an] <thing>`

`subscribe <phrase>`
* Bot will watch the chats that you share with it for any mentions of the keywords you specify
* Upon mention of a keyword, bot will send you a 1on1 with the context and group

`unsubscribe <phrase>`
* `<phrase>` is optional, if not specified `unsubscribe` will remove all subscriptions under your name
* If `<phrase>` is specified, `unsubscribe` will remove that phrase if it was previously subscribed to

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
