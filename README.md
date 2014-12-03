IMPORTANT
=========

This is a fork of https://github.com/xmikos/hangupsbot

* The build script is out-of-date and will be removed in the future.
  DO NOT TRUST IT ;)
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

Additional requirements:
* https://pypi.python.org/pypi/jsonrpclib-pelix `pip3 install jsonrpclib-pelix`
* https://pypi.python.org/pypi/pushbullet.py/0.5.0 `pip3 install pushbullet.py`

Quickstart for Users
====================
1. You need to open a 1-on-1 conversation with the bot first and say "hello" 
   (or anything!)
2. Then give yourself a @mention in another HO where the bot is participating 
   as a group member

This procedure is necessary to let the bot know you're alive ;P 

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
