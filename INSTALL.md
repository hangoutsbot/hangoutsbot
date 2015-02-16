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

1. start the bot with a valid gmail account (not your actual account!)
2. open a hangout with the bot (using your actual account), say anything to it
3. login into the bot's gmail account and ensure chat is activated
4. open up invites, and accept your incoming invite (from your actual account)
5. restart the bot and it will dump out a conversation and users list
6. find your actual account user name, the chat_id will be listed next to it

### with an existing bot

join a group with an existing bot and issue this command `/bot whoami`, your
chat_id will be displayed
