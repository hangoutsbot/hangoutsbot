# IMPORTANT

This is a fork of a [fork](https://gitlab.sabah.io/eol/mogunsamang/) of https://github.com/xmikos/hangupsbot

* To execute: `python3 hangupsbot.py`
* Any current tests will be in `<path of hangupsbot.py>/tests/`
* PushBullet integration is **experimental** - it also has a security risk: 
  since the only way to send pushes is via API key, the key has to be stored - 
  and is visible - inside `config.json`
  * To set your pushbullet key, open a 1-on-1 HO with the bot and issue:
    `/bot pushbulletapi [<api key>|false, 0, -1]`
    to set your api key or clear it, respectively.
* please also see the original documentation which is reproduced below
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

# Admins: Useful Commands
```
# add user 104...64 to the admins list...
/bot config append admins "104...64"  
/bot reload

# remove user 104...64 from the admins list...
/bot config remove admins "104...64"
/bot reload
```

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
