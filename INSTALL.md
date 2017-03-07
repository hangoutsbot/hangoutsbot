# Preparing your Environment

This section describes the most common way to prepare a system for Hangoutsbot and
  get it up and running.

**Docker Users:** See the the end of this file for the **Docker Usage** section.

1. Ensure that your system has Python 3.4.2 or newer - we recommend Python 3.5. It's
   most likely already installed on your system if you are using a fairly new Linux 
   distribution. The Python package manager `pip3` is also required and is usually 
   shipped with whatever version of Python your system comes with.
   * To check for the existence and versions of both the language and package manager,
     you can run the following commands at your terminal:
     * `python3 --version`
     * `pip3 --version`
   * For systems that don't have Python 3 pre-installed, it is usually available as a
     package that you can install 
       (e.g. `sudo apt-get install python3 python3-pip` on Debian/Ubuntu). 
     We do not provide any further guidance for installation as this is beyond the
     scope of the Hangoutsbot documentation and there are plenty of online resources
     which can cover more use-cases and OSes than we can ;)
2. Clone the repository:

   ```
   git clone <repository url>
   ```

3. Install the Python module dependencies that Hangoutsbot requires:

   ```
   cd hangoutsbot
   pip3 install -r requirements.txt
   ```

4. Run the program interactively for the first time - this topic is covered in the next
   section, so please go through it carefully.
5. Set up the bot to be run as a daemon/service so that it can run unattended and
   survive system reboots. This is an opiniated topic with plenty of different
   implementation methods. When you're ready, some scripts are available at the
   following links:
   * https://github.com/hangoutsbot/hangoutsbot/tree/master/examples
   * https://github.com/hangoutsbot/hangoutsbot/issues/69

# First-Run

You need to **run the bot for the first time**. You will need at least 
  two gmail accounts: one is your actual account, the other will be your 
  bot account.

The basic syntax for running the bot (assuming you are in the root 
  of the cloned repository) is:
```
python3 hangupsbot/hangupsbot.py
```
See https://github.com/tdryer/hangups/issues/260#issuecomment-246578670 for getting auth code

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
2. Send any message to the bot from your own gmail account.
3. On a browser, login into the bot's gmail account and ensure chat 
   is activated. Accept the invite (and message) from your own gmail
   account.
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


# Docker Usage

The bot can be run inside a docker container if desired.
You will need to create a directory outside the container to contain
configuration and storage data, and if you are using sinks, you may
need to change the ports we expose from the container (the defaults
are 9000, 9001, and 9002):

You will first need to build the image:

```
docker build -t hangoutsbot/hangoutsbot .
```

If you need to change ports add `--build-arg PORTS="new port list"`, for
example:

```
docker build -t hangoutsbot/hangoutsbot --build-arg PORTS="9000 9001 9002 9003 9004" .
```

Then you can run the image, any arguments starting with a "-" will be passed after
the image name will be passed on to the bot (e.g. `-d` for debug):

To run interactively, and in debug mode:

```
docker run -it -v $HOME/hob-data-dir:/data hangoutsbot/hangoutsbot -d
```

To run detatched, as a daemon:

```
docker run -d -v $HOME/hob-data-dir:/data hangoutsbot/hangoutsbot
```
