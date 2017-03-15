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

| platform | notes         | devs                                           | plugin base       |
|----------|---------------|------------------------------------------------|-------------------|
| hubot    | may be broken |                                                |                   |
| slack    | stable        | web-sink + external instance reference example | slack (legacy)    |
| telegram | stable        | asyncio longpoll example                       | telegram (legacy) |
| hangouts | stable        |                                                | syncrooms         |

# TODO/MISSING

* no image support yet
* proper documentation

*devs are invited to help fix these issues* :)

dev branch: https://github.com/hangoutsbot/hangoutsbot/tree/framework/context