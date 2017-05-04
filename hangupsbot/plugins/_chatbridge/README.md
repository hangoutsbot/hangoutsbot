# chatbridge-aware plugins

status: **experimental**

see https://github.com/hangoutsbot/hangoutsbot/wiki/Chatbridge-Framework

# stability

* chatbridges will work with the same config keys as their plugin base, where applicable
* do not run  both the base plugin and their chatbridge successor at the same time!

| platform | notes         | devs                                           | plugin base       |
|----------|---------------|------------------------------------------------|-------------------|
| hubot    | broken        |                                                |                   |
| slack    | stable        | web-sink + external instance reference example | slack (legacy)    |
| telegram | stable        | asyncio longpoll example                       | telegram (legacy) |
| hangouts | stable        |                                                | syncrooms         |
