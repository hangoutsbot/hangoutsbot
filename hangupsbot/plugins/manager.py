import asyncio, logging, json

import plugins

import cherrypy

logger = logging.getLogger(__name__)

def _initialise(bot):
    _start_manager(bot)

def _start_manager(bot):
    """will host a basic plugin manager at localhost:9090"""
    cherrypy.config.update({'server.socket_port': 9090})
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
        loaded_plugins = plugins.get_configured_plugins(self._bot)
        html = "<b>Loaded Plugins</b><br>"
        for plugin in loaded_plugins:
            html += "- {}<br>".format(plugin)
        return html

    index.exposed = True
