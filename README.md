HangupsBot
==========

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
