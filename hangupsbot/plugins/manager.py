import asyncio, logging, json

import plugins

import cherrypy
import os
from commands import command

logger = logging.getLogger(__name__)
loop =  asyncio.get_event_loop()
def _initialise(bot):
    
    print (loop)
    
    plugins.register_handler(_start_manager(bot,loop))


def _start_manager(bot,loop):
    """will host a basic plugin manager"""
    
    port = 9090
    path   = os.path.abspath(os.path.dirname(__file__))
    config = {

      '/manager' : {
        'tools.staticdir.on'            : True,
        'tools.staticdir.dir'           : os.path.join(path, 'manager')
        
      }
    }
    cherrypy.config.update(config)
    cherrypy.config.update({'server.socket_port': port})
    cherrypy.server.socket_host = '0.0.0.0' # cherrypy will listen on any ip
    # Start server
    cherrypy.tree.mount(PluginManager(bot), '/')
    cherrypy.engine.start()


class PluginManager(object):
    
    def __init__(self, bot):
        self._bot = bot
        self._loop = loop
    
    def index(self):
        return """<b>Bot Configuration</b>
                    <br><a href='/plugins'>Plugin Manager</a>
                    <br><a href='/conversations'>Conversation Manager</a>"""
           
    @cherrypy.expose
    def plugins(self):
        all_plugins = plugins.retrieve_all_plugins()
        loaded_plugins = plugins.get_configured_plugins(self._bot)
        
        html = """<html>
        <head></head>
          <body>
            <b>Loaded Plugins</b><br>
            <form method="get" action="plugins_submit">"""
        for plugin in all_plugins:
            if plugin in loaded_plugins:
                checked = " checked"
            else:
                checked = ""
            html += "<input type=\"checkbox\" name=\"plugin\" value=\"{0}\"{1}> {0}<br>".format(plugin, checked)

        html += """
              <button type="submit">Save</button>
            </form>
          </body>
        </html>"""
        return html

    @cherrypy.expose
    def conversations(self):
        all_conversations = self._bot.conversations.get()
        o2o_conversations = self._bot.conversations.get("type:ONE_TO_ONE")
        group_conversations = self._bot.conversations.get("type:GROUP")
        
        html = """<html>
        <head></head>
          <body>
            <H1>Conversations</H1>
            <form method="get" action="conversations_submit">
            <table style=\"width: 100%  ;\" >
            <tr>
            <th><H2>Group Conversations</H2></th>
            <th><H2>One to one Conversations</H2></th>
            </tr>
            <tr>
            <td style=\"vertical-align:top\">
            """
        for convid, convdata in group_conversations.items():
            html += "<input style=\"width: 90%  ;\" type=\"text\" name=\"conv\" value=\"{0}\"><img onclick=\"location.href='conv_rename?id={1}';\" height=\"16\" width=\"16\" alt=\"rename conversation\" src=\"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABEklEQVQ4T7WTvW3DMBBGvxOlOiPEGwTuVJCAN4lGcEbIBvIEpjfIBiZAFuqibOBskF4kGJxAAYZsmY6BsCOI9+6Hd4QHjpSyJaLeWqvpr7xSqgkh9EIIA2BLUsoNEe0BrJZkMcavsiw3/O69N0T0GULYFUXRsOBERM85OITQAohCiLckaccSlFKRYWvtYjlKKQ3gNQXRLDHG/PA9K5jBzByEENu7BEuw9/7onFvfzOAabK1tpJQ9Eb1MJV8tYQnmiPOeXQjqul5VVdUDeEpNO3Dk6ZeyAo7OX5YG5eMcviuDFEEPw/Dedd1pPh/ZDHKj/S8CnqipYbkExvcY47dzbtydcZkA6Fv7cG5lGEDjnONtxC86bbZsYHOH1gAAAABJRU5ErkJggg==\"/><img onclick=\"location.href='conv_leave?id={1}';\" height=\"16\" width=\"16\" alt=\"Leave conversation\" src=\"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAABAUlEQVRYR+2XQU7DQAxF/U/CEYC9R3Azyg3gJj1CqlhRdoQbhBvAOok+MiqVqJIMQ0tXHimLyOPxy1tk9CGFK6X0TvJFRCqSPcnXpmm6wmMO27HUqKr3InJ3XAewmesh6RC9iHQAqmEY3tq29ffVtQawAfCQOyBTd1sO9FzX9XZubxaA5M51fzf/BYrko5nNmvsNwI/mlBJLrQRAGAgDYSAMnN2AX8FmdqOqPYCr3K/5PwA6M7tVVb/pri8OkBt4XD+7gQAIA2EgDISBSxnwbOhPZWaHZFQYTD720eypOJotfeUSgF/RADwte0itxnHsTwqnKwBfgdOH+MBpmrpT4vknX/8GP+z8WWcAAAAASUVORK5CYII=\"/> <br>".format(convdata["title"],convid)

        html += "</td><td style=\"vertical-align:top\>"

        for convid, convdata in o2o_conversations.items():
            html += "<input style=\"width: 100%  ;\" type=\"text\" name=\"conv\" value=\"{0}\"> <br>".format(convdata["title"])

        html += "</td></tr></table>"

        html += """
              <button type="submit">Save</button>
            </form>
          </body>
        </html>"""
        return html

    @cherrypy.expose
    def plugins_submit(self, plugin):
        print("Plugins: {}".format(plugin))
        self._bot.config.set_by_path(["plugins"], plugin)
        self._bot.config.save()
        self._bot.config.load()
        return "Plugins successfully updated!<br><a href='/'>Back to bot configuration</a>"

    @cherrypy.expose
    def conv_leave(self, id):
        
         # workaround for missing event
        event = {'conv_id' : "blob" }
        
        
        print (loop)
        asyncio.async(command.run(self._bot, event, *["convleave", "id:" + id, " quietly"]),loop=loop)
        return "Left  !<br><a href='/'>Back to bot configuration</a>"

    @cherrypy.expose
    def conv_rename(self, id,topic):
        
         # workaround for missing event
        event = {'conv_id' : "blob" }
        
        
        print (loop)
        asyncio.async(command.run(self._bot, event, *["convrename", "id:" + id, " "+ topic]),loop=loop)
        return "Left  !<br><a href='/'>Back to bot configuration</a>"


    index.exposed = True


