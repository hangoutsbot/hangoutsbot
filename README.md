This branch is for HANGUPSBOT-HUBOT integration **only**

For the stable copy of HANGUPSBOT, please refer to the master branch.

**DO NOT MERGE THIS WITH MASTER**

# Background

Like everything else, this began with "why not implement..." and too much
spare time.

# Requirements

* A functional (and running!) version of [hubot](https://github.com/github/hubot).
  Configuring this is beyond the scope of this document. Please refer to the
  installation instructions on the GitHub repo.
* A functional (also running!) copy of hangupsbot.

# Recommendations

* Both hubot and hangupsbot should run on the same server to reduce network
  connectivity issues

# Setup

1. `git clone` ALL THE THINGS (as usual).
2. `git submodule update --init hubot-web` to retrieve the forked copy of
   hubot-web that is compatible with hangupsbot.
3. Proceed to your hubot folder, and execute `npm install hubot-web` - this
   acquires the dependencies for [hubot-web](https://www.npmjs.com/package/hubot-web)
   and installs the npm version (which we will modify shortly).
4. Important: Overwrite the installed version of
   `hubot/node_modules/hubot-web/index.coffee` with `hubot-web/index.coffee`
   from the forked version inside the submodule.
5. Modify your working hangupsbot config.json and add the following
   sinks/hooks:
```
"hooks": [
    {
        "config": {
            "HUBOT_URL": "http://127.0.0.1:8080/receive/"
        },
        "module": "hooks.hubotsend.post.sender"
    }
]
```
  and
```
"jsonrpc": [
    {
        "certfile": "/root/server.pem",
        "module": "sinks.hubotreceive.post.receiver",
        "name": "127.0.0.1",
        "port": 8081
    }
]
```

5. On the console in the hubot server, use the following configuration:
```
export HUBOT_HTML_RESPONSE="true"
export HUBOT_REST_SEND_URL="https://127.0.0.1:8081/"
```

6. Restart hubot with `bin/hubot --adapter web`. You will not get a shell
   prompt, the server will just start and become non-interactive.
7. Restart hangupsbot, and ensure that the new sink and hook starts properly.

# Testing integration

Open your hangout with hangupsbot, and type a standard hubot command
  e.g. `hubot time`, `hubot ping`. After a brief lag, you should see hubot's
  responses in the hangout.
