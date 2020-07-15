# chatbridge-aware plugins

status: **experimental**

see https://github.com/hangoutsbot/hangoutsbot/wiki/Chatbridge-Framework

# general notes

* chatbridges will work with the same config keys as their plugin base, where applicable
  * advanced plugins may migrate configurations automatically
* do not run  both the base plugin and their chatbridge successor at the same time!
* documentation for each plugin is on their own wiki pages

# base plugins

* located in this folder, useful for basic integration

name                 | platform | stability | devs                                           | v2 plugin base |
---------------------|----------|-----------|------------------------------------------------|----------------|
chatbridge_slack     | slack    | stable    | web-sink + external instance reference example | slack          |
chatbridge_telegram  | telegram | stable    | asyncio longpoll example                       | telegram       |
chatbridge_syncrooms | hangouts | stable    |                                                | syncrooms      |

# other compatible plugins

* located outside of this folder, may be moved before release
* implements more feature-rich integration

name     | platform | stability | devs               | v2 plugin base |
---------|----------|-----------|--------------------|----------------|
telesync | telegram | stable    |                    | telesync       |
slackrtm | slack    | stable    | undergoing rewrite | slackrtm       |
