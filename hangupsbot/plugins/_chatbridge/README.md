# chat bridge plugins

status: **experimental**

chat platform bridging plugins that:

* interoperate without being cognisant of each other
* allows abitrary chaining without need for supergroup
* transparent traversal of bot command results
* unified api model based on updated webbridge

# relaying model

"broadcast-relay" model utilising `allmessages` and `sending` handler

more info: https://github.com/hangoutsbot/hangoutsbot/wiki/WIP:-Chatbridge-API-Standardisation

# stability

* chatbridges will work with the same config keys as their plugin base, where applicable
* do not run  both the base plugin and their chatbridge successor at the same time!

| platform | notes         | devs                                           | plugin base       |
|----------|---------------|------------------------------------------------|-------------------|
| hubot    | may be broken |                                                |                   |
| slack    | stable        | web-sink + external instance reference example | slack (legacy)    |
| telegram | stable        | asyncio longpoll example                       | telegram (legacy) |
| hangouts | stable        |                                                | syncrooms         |

# TODO/MISSING

* more control over source user/platform and message formatting
* html/markdown processing
* no image support yet
* proper documentation

*devs are invited to help fix these issues* :)

* sporadic comments in the source code
* dev branch: https://github.com/hangoutsbot/hangoutsbot/tree/framework/context
