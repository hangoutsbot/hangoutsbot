# IMPORTANT

This is a fork of a [fork](https://gitlab.sabah.io/eol/mogunsamang/) of https://github.com/xmikos/hangupsbot

* To execute: `python3 hangupsbot.py`
* Any current tests will be in `<path of hangupsbot.py>/tests/`
* Please see the original documentation which is reproduced below
  (after the TODO section)

Additional requirements:
* https://pypi.python.org/pypi/jsonrpclib-pelix `pip3 install jsonrpclib-pelix`
* https://pypi.python.org/pypi/pushbullet.py/0.5.0 `pip3 install pushbullet.py`

# Users: Quickstart

1. You need to open a 1-on-1 conversation with the bot first and say "hello" 
   (or anything!)
2. Then give yourself a @mention in another HO where the bot is participating 
   as a group member

This procedure is necessary to let the bot know you're alive ;P 
No seriously, the above steps are **required** to authorise two-way 
communication between the bot and your own account.

# Admins: Installation & Configuration

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

# Bot Commands

All bot commands must be prefixed by `/bot`, as in `/bot <command>`.

## Administrative Commands

These are commands that can only be executed by admins, based on the default
configuration in `config.commands_admin`.

`users` 
* Bot lists all users in current conversation.
* List will contain user G+ profile link and email (if available).

`user <string name>` 
* Bot searches for users whose names contain <string> in internal user list.
* Spaces are not allowed.
* The bot will search all users in all participating conversations.

`hangouts`
* Bot lists all participating conversations with additional details.
* Legend: c = commands enabled; f = forwarding enabled; a = auto-replies.

`rename <string title>`
* Bot renames the current conversation. 
* Spaces in the title are allowed.
* Works with both 1-on-1 or group conversations.
* Note: 1-on-1 renames may not reflect their title properly on desktop clients.

`leave [<conversation id>]`
* Bot leaves the current hangout if <conversation id> not specified.

`easteregg <ponies|pitchforks|bikeshed|shydino> <number> <period>`
* Bot activates Hangouts easter-egg animation (varies by client).
* <number> is the amount of repetition with delay of <period> in seconds.

`quit`
* Kills the running bot process on the server with a disconnection.

`config get <key> [<subkey> [...]]`
* Bot reads config.json and displays contents of `config.<key>[.<subkey>...]`

`config set <key> [<subkey> [...]] "<value>"`
* Bot sets contents of `config.<key>[.<subkey>...]` to `<value>`
* `<value>` must be enclosed in double-quotes and is interpreted as JSON.
* Changes are saved instantly into `config.json`.
* WARNING: This command is low-level and can scramble the configuration.

`config append <key> [<subkey> [...]]` "<value>"`
* Bot appends <value> to list at `config.<key>[.<subkey>...]`
* `<value>` must be enclosed in double-quotes and is interpreted as JSON.
* Only works if the key pointed at is an actual list.
* Usually used to add administrator ids to `config.admins`
* WARNING: This command is low-level and can scramble the configuration.

`config remove <key> [<subkey> [...]]` "<value>"`
* Bot removes specified <value> from list at `config.<key>[.<subkey>...]`
* `<value>` must be enclosed in double-quotes and is interpreted as JSON.
* Only works if the key pointed at is an actual list.
* Usually used to remove administrator ids from `config.admins`
* WARNING: This command is low-level and can scramble the configuration.

## Standard Commands

These are commands that can be executed by any user, based on the default
configuration in `config.commands_admin`.

`help` 
* Bot lists all supported commands.

`ping` 
* Bot replies with a `pong.

`echo <string anything>`
* Bot replies with <string> as the message.
* Spaces are allowed.

`pushbulletapi <apikey>`
* Sets the pushbullet api key for current user.
* When user is @mentioned, bot will alert user through PushBullet.
* If the push fails, bot will revert to normal hangouts-based alert.
  
`pushbullet <false|0|-1>`
* Disables pushbullet integration for current user.

`dnd`
* Toggles global DND (Do Not Disturb) for current user.
* Bot will message user whether DND is toggled on or off.
* User will not receive alerts for @mentions.

'whoami'
* Bot replies with the full name and `chat_id` of the current user.

`whereami`
* Bot replies with the conversation name and `conversation id`.

`mention <name fragment>`
* Alias for @<name fragment>.
* Triggers the same mechanisms for @mentions.
* `<name fragment>` cannot contain spaces.
* Like @mentions, `<name fragment>` matches combined first name and last name.

# Developers: Extending the Bot

## Adding Hooks

Hooks allow extension of bot functionality by adding modular packages which
contain class methods. These methods are called on common chat events:
* `init`, called when the hook is first loaded (one-time per run)
* `on_chat_message`
* `on_membership_change`
* `on_rename`

A fully-functional chat logger is provided as part of the repo, and can be 
found in `hangoutsbot/hooks/chatlogger/writer.php`. The chat logger logs each
chat the bot is operating in inside separate text files.

Note that hooks can use `config.json` as a configuration source as well. In 
the case of the example chat logger, the following configuration is necessary:
```
...,
"hooks": [
{
  "module": "hooks.chatlogger.writer.logger",
  "config": 
  {
    "storage_path": "<location to store chat log files>"
  }
}
],
...
```

## Adding your own (Web-Hook) Sinks

Sinks allow the bot to receive external events in the form of JSON-based web
requests. Presently the bot comes pre-packaged with several sinks:
* GitLab-compatible web hook sink that post git pushes in a hangout
* GitHub-compatible web hook sink that post git pushes in a hangout
* demo implementation that works with `hangupsbot/tests/send.py`

The sink/receiver is based on `BaseHTTPRequestHandler` - 
`hangoutsbot/sinks/generic/simpledemo.py` is a very basic example.
Some recommendations:
* Always use SSL/TLS, a self-signed certificate is better than nothing
* Setting `config.jsonrpc[].name` to "127.0.0.1" will start the sink but only
  allow connections from localhost - use this to debug potentially unsafe sinks.

### GitLab Users: Web Hook Sink/Receiver

As noted previously, a GitLab-compatible sink is available for posting pushes into
a hangout - these are the configuration instructions:

#### configuring and starting the sink

Important: Still under development, subject to change

1. Generate a .pem file for SSL/TLS. It can be generated anywhere
   accessible to the script. **This is a mandatory step** as the sink will refuse
   to start without SSL/TLS. A self-signed certificate will do:
   ```
   openssl req -new -x509 -keyout server.pem -out server.pem -days 365 -nodes
   ```

2. Open the bot's `config.json` file and modify the `jsonrpc` key as follows:
   ```
   ...,
   "jsonrpc": [
     {
       "module": "sinks.gitlab.simplepush.webhookReceiver",
       "certfile": "<location of .pem file>",
       "port": 8000
     }
   ],
   ...
   ```

3. (Re-)start the bot

#### configuring gitlab

1. Determine which group hangout you want to receive GitLab events. In that 
   hangout, execute `/bot whereami` - the bot will message the id for that 
   specific hangout. Record the conversation id.
2. In your GitLab instance, access Project Settings > Web Hooks
3. Select which project events you want to be notified of and specify this URL:
   ```
   https://<your bot ip/domain name>:8000/<conversation id>/
   ```
   
4. After entering the above, **Add Web Hook**, then test the hook.

# Developers: TODO

* easier setup/configuration
* run as service ([cron](http://www.raspberrypi-spy.co.uk/2013/07/running-a-python-script-at-boot-using-cron/) works too!)
* better debug output

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
