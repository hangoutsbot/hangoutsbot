# IMPORTANT

This is a fork of a [fork](https://gitlab.sabah.io/eol/mogunsamang/) of https://github.com/xmikos/hangupsbot

* To execute: `python3 hangupsbot.py`
  * If the script cannot find `config.json`, execute 
    `<path of hangupsbot.py>/python3 hangupsbot.py --config ../config.json`
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

# Developers: Adding your own Web Hook Sinks

In the `hangoutsbot/sinks/` folder are additional packages you can reference.
The imlementation of a sink/receiver is derived from `BaseHTTPRequestHandler`.
See `hangoutsbot/sinks/generic/simpledemo.py` for a basic example.
Some recommendations:
* Always use SSL/TLS, a self-signed certificate is better than nothing
* Setting `config.jsonrpc[].name` to "127.0.0.1" will start the sink but only
  allow connections from localhost - use this to debug potentially unsafe sinks.

# GitLab Users: Web Hook Sink/Receiver

Partial support as a "sink" (receiver) for gitlab project webhooks is available. These
are preliminary instructions how to setup a webhook sink:

## configuring and starting the sink

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

## configuring gitlab

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
* integration with gitlab (in progress)
* secure json-rpc
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
