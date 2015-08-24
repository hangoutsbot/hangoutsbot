# Preparing your Environment

**install python 3.4 from source**
```
wget https://www.python.org/ftp/python/3.4.2/Python-3.4.2.tgz
tar xvf Python-3.4.2.tgz
cd Python-3.4.2
./configure
make
make test
sudo make install
```

**git clone the repository**
```
git clone <repository url>
```

**install dependencies**
```
pip3 install -r requirements.txt
```

Note: `pip` may install an outdated version of hangups. You may have to 
  install directly from [source](https://github.com/tdryer/hangups).
  Related: https://github.com/nylonee/hangupsbot/issues/43#issuecomment-72794942

# First-Run

You need to **run the bot for the first time**. You will need at least 
  two gmail accounts: one is your actual account, the other will be your 
  bot account.

The basic syntax for running the bot (assuming you are in the root 
  of the cloned repository) is:
```
python3 hangupsbot/hangupsbot.py
```

If you are having problems starting the bot, appending a `-d` at the
  end will dump more details into the bot logs e.g. 
  `python3 hangupsbot/hangupsbot.py -d` - more configuration 
  directives can be found at the end of the README file.

You will be prompted for your gmail username and password. Use your
  bot account credentials. If the login is sucessful, you will see
  additional logs about plugins being loaded. The credentials will be
  saved so that running the bot again will not prompt you for username
  and password again.

To quit the bot from the console, press CTRL-C

# Initial Configuration

DO NOT EDIT the `config.json` supplied with the bot. It is the 
  reference file used to generate the actual config file, which
  is located elsewhere. Please see the next section on 
  **Additional Configuration** to get the location of the 
  actual configuration file if you need to edit it manually.

You will need to add your actual Hangouts user as a bot administrator.

This will be accomplished using the supplied **starter** plugin with
  the default supplied configuration.

1. Using a hangouts client and your actual gmail account, open a 
   hangout with the bot account.
2. Send any message to the bot.
3. On a browser, login into the bot's gmail account and ensure chat 
   is activated. Accept the invite from your actual account.
4. Back on your hangouts client, send the following message:
   `/bot iamspartacus`
5. The bot should reply with "configuring first admin" or a similar
   message.

# Additional Configuration

After the first successful run of the bot, it should generate a 
  `config.json` somewhere in your user directory.

You should be able to find it in: 
  `/<username>/.local/share/hangupsbot/`, where <username> is your
  operating system username.

You can edit this file and restart the bot to load any new configs.

For further information, please see the README file and wiki.

# Troubleshooting

* For console output when the bot is starting, errors messages always
  start in ALLCAPS e.g. "EXCEPTION in ..."
* Additional logs can be found in: 
  `/<username>/.local/share/hangupsbot/hangupsbot.log` - 
  note: this file is more useful for developers and may be quite verbose
* You can verify the location of your active `config.json` by sending
  the following command to the bot via hangouts: `/bot files` (with
  the **starter** plugin active)
