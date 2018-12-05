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

            """command: argument preprocessors"""
            if len(plugin["commands"]["argument.preprocessors"]) > 0:
                lines.append( "<b>command preprocessor groups:</b> "
                              ", ".join(plugin["commands"]["argument.preprocessors"]) )

        if len(lines) > 0:
            text_plugins.append("<br />".join(lines))

    if len(text_plugins) > 0:
        message = "<br />".join(text_plugins)
    else:
        message = "nothing to display"

    yield from bot.coro_send_message(event.conv_id, message)


@command.register(admin=True)
def pluginunload(bot, event, *args):
    """unloads a previously unloaded plugin, requires plugins. prefix"""

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
    """loads a previously unloaded plugin, requires plugins. prefix"""

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
    """reloads a previously loaded plugin, requires plugins. prefix"""

    if args:
        module_path = args[0]

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
def getplugins(bot, event, *args):
    """list all plugins loaded by the bot, and all available plugins"""

    config_plugins = bot.config.get_by_path(["plugins"]) or False
    if not isinstance(config_plugins, list):
        yield from bot.coro_send_message(
            event.conv_id,
            "this command only works with manually-configured plugins key in config.json")
        return

    lines = []
    all_plugins = plugins.retrieve_all_plugins(allow_underscore=True) or []
    loaded_plugins = plugins.get_configured_plugins(bot) or []

    lines.append("**{} loaded plugins (config.json)**".format(len(loaded_plugins)))

    for _plugin in sorted(loaded_plugins):
        lines.append("* {}".format(_plugin.replace("_", "\\_")))

    lines.append("**{} available plugins**".format(len(all_plugins)))

    for _plugin in sorted(all_plugins):
        if _plugin not in loaded_plugins:
            lines.append("* {}".format(_plugin.replace("_", "\\_")))

    yield from bot.coro_send_message(event.conv_id, "\n".join(lines))


def _strip_plugin_path(path):
    """remove "plugins." prefix if it exist"""
    return path[8:] if path.startswith("plugins.") else path


@command.register(admin=True)
def removeplugin(bot, event, plugin, *args):
    """unloads a plugin from the bot and removes it from the config, does not require plugins. prefix"""

    config_plugins = bot.config.get_by_path(["plugins"]) or False
    if not isinstance(config_plugins, list):
        yield from bot.coro_send_message(
            event.conv_id,
            "this command only works with manually-configured plugins key in config.json")
        return

    lines = []
    loaded_plugins = plugins.get_configured_plugins(bot) or []
    all_plugins = plugins.retrieve_all_plugins(allow_underscore=True)

    lines.append("**remove plugin: {}**".format(plugin.replace("_", "\\_")))

    plugin = _strip_plugin_path(plugin)

    if not plugin:
        yield from bot.coro_send_message(
            event.conv_id,
            "invalid plugin name")
        return

    if plugin not in all_plugins:
        yield from bot.coro_send_message(
            event.conv_id,
            "plugin does not exist: {}".format(plugin.replace("_", "\\_")) )
        return

    if plugin in loaded_plugins:
        try:
            module_path = "plugins.{}".format(plugin)
            escaped_module_path = module_path.replace("_", "\\_")
            yield from plugins.unload(bot, module_path)
            lines.append('* **unloaded: {}**'.format(escaped_module_path))
        except (RuntimeError, KeyError) as e:
            lines.append('* error unloading {}: {}'.format(escaped_module_path, str(e)))
    else:
        lines.append('* not loaded on bot start')

    if plugin in config_plugins:
        config_plugins.remove(plugin)
        bot.config.set_by_path(["plugins"], config_plugins)
        bot.config.save()
        lines.append('* **removed from config.json**')
    else:
        lines.append('* not in config.json')

    if len(lines) == 1:
        lines = [ "no action was taken for {}".format(plugin.replace("_", "\\_")) ]

    yield from bot.coro_send_message(event.conv_id, "\n".join(lines))


@command.register(admin=True)
def addplugin(bot, event, plugin, *args):
    """loads a plugin on the bot and adds it to the config, does not require plugins. prefix"""

    config_plugins = bot.config.get_by_path(["plugins"]) or False
    if not isinstance(config_plugins, list):
        yield from bot.coro_send_message(
            event.conv_id,
            "this command only works with manually-configured plugins key in config.json" )
        return

    lines = []
    loaded_plugins = plugins.get_configured_plugins(bot) or []
    all_plugins = plugins.retrieve_all_plugins(allow_underscore=True)

    plugin = _strip_plugin_path(plugin)

    if not plugin:
        yield from bot.coro_send_message(
            event.conv_id,
            "invalid plugin name")
        return

    if plugin not in all_plugins:
        yield from bot.coro_send_message(
            event.conv_id,
            "plugin does not exist: {}".format(plugin.replace("_", "\\_")) )
        return

    lines.append("**add plugin: {}**".format(plugin.replace("_", "\\_")))

    if plugin in loaded_plugins:
        lines.append('* already loaded on bot start')
    else:
        module_path = "plugins.{}".format(plugin)
        escaped_module_path = module_path.replace("_", "\\_")
        try:
            if plugins.load(bot, module_path):
                lines.append('* **loaded: {}**'.format(escaped_module_path))
            else:
                lines.append('* failed to load: {}'.format(escaped_module_path))
        except RuntimeError as e:
            lines.append('* error loading {}: {}'.format(escaped_module_path, str(e)))

    if plugin in config_plugins:
        lines.append('* already in config.json')
    else:
        config_plugins.append(plugin)
        bot.config.set_by_path(["plugins"], config_plugins)
        bot.config.save()
        lines.append('* **added to config.json**')

    yield from bot.coro_send_message(event.conv_id, "\n".join(lines))
