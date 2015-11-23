import asyncio, logging, json

import plugins

import cherrypy

logger = logging.getLogger(__name__)

def _initialise(bot):
    _start_manager(bot)

def _start_manager(bot):
    """will host a basic plugin manager at localhost:9090"""
    cherrypy.config.update({'server.socket_port': 9093})
    # Start server
    cherrypy.tree.mount(PluginManager(bot), '/')
    cherrypy.engine.start()

class PluginManager(object):
    def __init__(self, bot):
        self._bot = bot

    def index(self):
        return "Hello World!"

    @cherrypy.expose
    def plugins(self):
        all_plugins = plugins.retrieve_all_plugins()
        loaded_plugins = plugins.get_configured_plugins(self._bot)
        html = "<b>Loaded Plugins</b><br>"
        for plugin in all_plugins:
            if plugin in loaded_plugins:
                checked = " checked"
            else:
                checked = ""
            html += "<input type=\"checkbox\" name=\"plugin\" value=\"{0}\"{1}> {0}<br>".format(plugin, checked)
        return html

    index.exposed = True
