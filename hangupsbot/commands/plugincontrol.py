import logging

import plugins
import handlers

from commands import command


logger = logging.getLogger(__name__)


def _initialise(bot): pass # prevents commands from being automatically added


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
                lines.append("<br />".join([ "... <b><pre>{}</pre></b> (<pre>{}</pre>, p={})".format(f[0].__name__, f[1], str(f[2])) for f in plugin["handlers"]]))

            """shared"""
            if len(plugin["shared"]) > 0:
                lines.append("<b>shared:</b> " + ", ".join([ "<pre>{}</pre>".format(f[1].__name__) for f in plugin["shared"]]))

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
