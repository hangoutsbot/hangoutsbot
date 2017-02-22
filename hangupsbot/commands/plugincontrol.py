import logging

import plugins
import handlers

from commands import command


logger = logging.getLogger(__name__)


def _initialise(bot): pass # prevents commands from being automatically added

def function_name(fn):
    try:
        # standard function
        return fn.__name__
    except AttributeError:
        try:
            # lambda
            return fn.func_name
        except AttributeError:
            try:
                # functools.partial
                return function_name(fn.func)
            except AttributeError:
                return '<unknown>'

def _get_module_path(path, return_full_module=True):
    """return the module path in a str. This allows functionality to
    load a plugin both from `plugins.default` format, as well as `plugins` format.
    NOTE: this assumes that all plugins to load/unload are within the plugins folder"""

    module_path = path.split(".")

    if module_path[0] != "plugins":
        module_path = ["plugins"] + module_path

    return ".".join(module_path) if return_full_module else ".".join(module_path[1:])

@command.register(admin=True)
def plugininfo(bot, event, *args):
    """dumps plugin information"""
    text_plugins = []

    for module_path, plugin in plugins.tracking.list.items():
        lines = []
        if len(args) == 0 or args[0] in plugin["metadata"]["module"] or args[0] in module_path:
            lines.append("<b>[ {} ]</b>".format(plugin["metadata"]["module.path"]))

            """admin commands"""
            if len(plugin["commands"]["admin"]) > 0:
                lines.append("<b>admin commands:</b> <pre>{}</pre>".format(", ".join(plugin["commands"]["admin"])))

            """user-only commands"""
            user_only_commands = list(set(plugin["commands"]["user"]) - set(plugin["commands"]["admin"]))
            if len(user_only_commands) > 0:
                lines.append("<b>user commands:</b> <pre>{}</pre>".format(", ".join(user_only_commands)))

            """handlers"""
            if len(plugin["handlers"]) > 0:
                lines.append("<b>handlers:</b>")
                lines.append("<br />".join([ "... <b><pre>{}</pre></b> (<pre>{}</pre>, p={})".format(function_name(f[0]), f[1], str(f[2])) for f in plugin["handlers"]]))

            """shared"""
            if len(plugin["shared"]) > 0:
                lines.append("<b>shared:</b> " + ", ".join([ "<pre>{}</pre>".format(function_name(f[1])) for f in plugin["shared"]]))

            """threads"""
            if len(plugin["threads"]) > 0:
                lines.append("<b>threads:</b> {}".format(len(plugin["threads"])))

            """aiohttp.web"""
            if len(plugin["aiohttp.web"]) > 0:
                lines.append("<b>aiohttp.web:</b>")
                from sinks import aiohttp_list
                filtered = aiohttp_list(plugin["aiohttp.web"])
                if len(filtered) > 0:
                    lines.append('<br />'.join([ '... {}'.format(constructors[0].sockets[0].getsockname())
                                                 for constructors in filtered ]))
                else:
                    lines.append('<em>no running aiohttp.web listeners</em>')

            """tagged"""
            if len(plugin["commands"]["tagged"]) > 0:
                lines.append("<b>tagged via plugin module:</b>")
                for command_name, type_tags in plugin["commands"]["tagged"].items():
                    if 'admin' in type_tags:
                        plugin_tagsets = type_tags['admin']
                    else:
                        plugin_tagsets = type_tags['user']

                    matches = []
                    for tagset in plugin_tagsets:
                        if isinstance(tagset, frozenset):
                            matches.append("[ {} ]".format(', '.join(tagset)))
                        else:
                            matches.append(tagset)

                    lines.append("... <b><pre>{}</pre></b>: <pre>{}</pre>".format(command_name, ', '.join(matches)))

        if len(lines) > 0:
            text_plugins.append("<br />".join(lines))

    if len(text_plugins) > 0:
        message = "<br />".join(text_plugins)
    else:
        message = "nothing to display"

    yield from bot.coro_send_message(event.conv_id, message)

@command.register(admin=True)
def pluginall(bot, event, *args):
    """list all plugins loaded by the bot, and all available plugins"""
    all_plugins = plugins.retrieve_all_plugins()
    loaded_plugins = plugins.get_configured_plugins(bot)

    message = "The following plugins are loaded:<br />"

    for plugin in sorted(loaded_plugins):
        message += "<b>{}</b><br />".format(plugin)

    message += "<br />Available plugins:<br />"

    for plugin in sorted(all_plugins):
        if plugin not in loaded_plugins:
            message += "<i>{}</i><br />".format(plugin)

    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def pluginunload(bot, event, *args):
    if args:
        module_path = args[0]

        try:
            yield from plugins.unload(bot, module_path)
            message = "<b><pre>{}</pre>: unloaded</b>".format(module_path)

        except (RuntimeError, KeyError) as e:
            message = "<b><pre>{}</pre>: <pre>{}</pre></b>".format(module_path, str(e))

    else:
        message = "<b>module path required</b>"

    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def pluginload(bot, event, *args):
    if args:
        module_path = args[0]

        try:
            if plugins.load(bot, module_path):
                message = "<b><pre>{}</pre>: loaded</b>".format(module_path)
            else:
                message = "<b><pre>{}</pre>: failed</b>".format(module_path)

        except RuntimeError as e:
            message = "<b><pre>{}</pre>: <pre>{}</pre></b>".format(module_path, str(e))

    else:
        message = "<b>module path required</b>"

    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def pluginreload(bot, event, *args):
    if args:
        module_path = _get_module_path(plugin)

        try:
            yield from plugins.unload(bot, module_path)
            if plugins.load(bot, module_path):
                message = "<b><pre>{}</pre>: reloaded</b>".format(module_path)
            else:
                message = "<b><pre>{}</pre>: failed reload</b>".format(module_path)

        except (RuntimeError, KeyError) as e:
            message = "<b><pre>{}</pre>: <pre>{}</pre></b>".format(module_path, str(e))

    else:
        message = "<b>module path required</b>"

    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def removeplugin(bot, event, plugin, *args):
    """unloads a plugin from the bot and removes it from the config"""
    value = bot.config.get_by_path(["plugins"])
    if isinstance(value, list):
        try:
            value.remove(_get_module_path(plugin, return_full_module=False))
            bot.config.set_by_path(["plugins"], value)
            bot.config.save()

            pluginunload(bot, event, _get_module_path(plugin))
            message = "Plugin successfully unloaded"
        except ValueError:
            message = "Plugin not loaded"
    else:
        message = "Plugin config not set"

    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def addplugin(bot, event, plugin, *args):
    """loads a plugin on the bot and adds it to the config"""
    all_plugins = plugins.retrieve_all_plugins()
    loaded_plugins = plugins.get_configured_plugins(bot)
    if _get_module_path(plugin, return_full_module=False) not in loaded_plugins:
        if _get_module_path(plugin, return_full_module=False) in all_plugins:
            value = bot.config.get_by_path(["plugins"])
            if isinstance(value, list):
                value.append(_get_module_path(plugin, return_full_module=False))
                bot.config.set_by_path(["plugins"], value)
                bot.config.save()

                # load the plugin
                pluginload(bot, event, _get_module_path(plugin))
                message = "Plugin successfully loaded"
            else:
                message = "Error: Do <b>/bot config set plugins []</b> first"
        else:
            message = "Not a valid plugin name"
    else:
        message = "Plugin already loaded"

    yield from bot.coro_send_message(event.conv_id, message)
