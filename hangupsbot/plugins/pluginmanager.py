import re, json, logging

import hangups

import plugins

from commands import command

logger = logging.getLogger(__name__)

def _initialise(bot):
    plugins.register_admin_command(["getplugins", "addplugin", "removeplugin"])

def getplugins(bot, event, *args):
    """List all plugins loaded by the bot, and all available plugins"""
    all_plugins = plugins.retrieve_all_plugins()
    loaded_plugins = plugins.get_configured_plugins(bot)

    html = """The following plugins are loaded:<br />"""

    for plugin in sorted(loaded_plugins):
        html += "<b>{}</b><br />".format(plugin)

    html += """<br />Available plugins:<br />"""

    for plugin in sorted(all_plugins):
        if plugin not in loaded_plugins:
            html += "<i>{}</i><br />".format(plugin)

    yield from bot.coro_send_to_user_and_conversation(event.user_id.chat_id, event.conv_id, html, "<i>I've sent you a private message</i>")

def addplugin(bot, event, plugin, *args):
    """Adds a plugin to the bot, REQUIRES REBOOT
    /bot addplugin <pluginname>"""
    all_plugins = plugins.retrieve_all_plugins()
    loaded_plugins = plugins.get_configured_plugins(bot)

    if plugin not in loaded_plugins:
        if plugin in all_plugins:
            value = bot.config.get_by_path(["plugins"])
            if isinstance(value, list):
                value.append(plugin)
                bot.config.set_by_path(["plugins"], value)
                bot.config.save()

                # attempt to load the plugin
                try:
                    if plugins.load(bot, "plugins.{}".format(plugin)):
                        message = "<b><pre>{}</pre>: loaded</b>".format("plugins.{}".format(plugin))
                    else:
                        message = "<b><pre>{}</pre>: failed</b>".format("plugins.{}".format(plugin))

                except RuntimeError as e:
                    message = "<b><pre>{}</pre>: <pre>{}</pre></b>".format(module_path, str(e))

            else:
                message = "Error: Do <b>/bot config set plugins []</b> first"
        else:
            message = "Not a valid plugin name"
    else:
        message = "Plugin already loaded"
    yield from bot.coro_send_message(event.conv_id, message)


def removeplugin(bot, event, plugin, *args):
    """Removes a plugin from the bot, REQUIRES REBOOT
    /bot removeplugin <pluginname>"""
    value = bot.config.get_by_path(["plugins"])
    if isinstance(value, list):
        try:
            value.remove(plugin)
            bot.config.set_by_path(["plugins"], value)
            bot.config.save()

            yield from plugins.unload(bot, "plugins.{}".format(plugin))
            message = "<b><pre>{}</pre>: unloaded</b>".format("plugins.{}".format(plugin))
        except ValueError:
            message = "Plugin not loaded"
        except (RuntimeError, KeyError) as e:
            message = "<b><pre>{}</pre>: <pre>{}</pre></b>".format("plugins.{}".format(plugin), str(e))
    else:
        message = "Plugin config not set"


    yield from bot.coro_send_message(event.conv_id, message)
