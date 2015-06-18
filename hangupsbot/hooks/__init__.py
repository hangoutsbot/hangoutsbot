import logging

from utils import class_from_name

def load(bot):
    hook_packages = bot.get_config_option('hooks')
    itemNo = -1
    bot._hooks = []

    if isinstance(hook_packages, list):
        for hook_config in hook_packages:
            try:
                module = hook_config["module"].split(".")
                if len(module) < 4:
                    print(_("config.hooks[{}].module should have at least 4 packages {}").format(itemNo, module))
                    continue
                module_name = ".".join(module[0:-1])
                class_name = ".".join(module[-1:])
                if not module_name or not class_name:
                    print(_("config.hooks[{}].module must be a valid package name").format(itemNo))
                    continue
            except KeyError as e:
                print(_("config.hooks[{}] missing keyword").format(itemNo), e)
                continue

            theClass = class_from_name(module_name, class_name)
            theClass._bot = bot
            if "config" in hook_config:
                # allow separate configuration file to be loaded
                theClass._config = hook_config["config"]

            if theClass.init():
                print(_("_load_hooks(): {}").format(module))
                bot._hooks.append(theClass)
            else:
                print(_("_load_hooks(): hook failed to initialise"))

    message = _("_load_hooks(): {} hook(s) loaded").format(len(bot._hooks))
    logging.info(message)
