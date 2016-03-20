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

    for plugin in loaded_plugins:
        html += "<b>{}</b><br />".format(plugin)

    html += """<br />Available plugins:<br />"""

    for plugin in all_plugins:
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
                yield from bot.coro_send_message(event.conv_id, "Plugin <i>{}</i> added".format(plugin))
            else:
                yield from bot.coro_send_message(event.conv_id, "Error: Do <b>/bot config set plugins []</b> first")
        else:
            yield from bot.coro_send_message(event.conv_id, "Not a valid plugin name")
    else:
        yield from bot.coro_send_message(event.conv_id, "Plugin already loaded")

def removeplugin(bot, event, plugin, *args):
    """Removes a plugin from the bot, REQUIRES REBOOT
    /bot removeplugin <pluginname>"""
    value = bot.config.get_by_path(["plugins"])
    if isinstance(value, list):
        try:
            value.remove(plugin)
        except ValueError:
            yield from bot.coro_send_message(event.conv_id, "Plugin not loaded")
            return
        bot.config.set_by_path(["plugins"], value)
        bot.config.save()
        yield from bot.coro_send_message(event.conv_id, "Plugin <i>{}</i> removed".format(plugin))
    else:
        yield from bot.coro_send_message(event.conv_id, "Plugin config not set")

