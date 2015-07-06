import datetime

import plugins

import utils

from hangups.ui.utils import get_conv_name as hangups_get_conv_name

convmem = {}

def _initialise(bot):
    utils._conversation_list_cache = convmem # !!!: it works, but i don't like it ;P
    _memory_load(bot)
    _update_conversation_list(bot)
    plugins.register_admin_command(["dumpconv"])
    plugins.register_handler(_watch_message, type="allmessages")
    plugins.register_handler(_watch_rename, type="rename")
    plugins.register_handler(_watch_member, type="membership")
    plugins.register_shared('convmem.removeconv', _conv_remove)

def _update_conversation_list(bot):
    for conv in bot._conv_list.get_all():
        _conv_update(bot, conv, source="init")

def _watch_rename(bot, event, command):
    _conv_update(bot, event.conv, source="renm")

def _watch_message(bot, event, command):
    _conv_update(bot, event.conv, source="chat")

def _watch_member(bot, event, command):
    _conv_update(bot, event.conv, source="mmbr")


def _conv_update(bot, conv, source="unknown"):
    conv_title = hangups_get_conv_name(conv)
    if conv.id_ not in convmem:
        convmem[conv.id_] = {}
    convmem[conv.id_] = {
        "title": conv_title,
        "source": source,
        "users" : [], # uninitialised
        "updated": datetime.datetime.now().strftime("%Y%m%d%H%M%S")}
    convmem[conv.id_]["users"] = [[ user.id_, user.full_name ] for user in conv.users if not user.is_self] # expensive to store
    _memory_save(bot)

def _conv_remove(bot, convid):
    if convid in convmem:
        del(convmem[convid])
        print("convmem: removing {}".format(convid))
        _memory_save(bot)


def _memory_save(bot):
    bot.memory.set_by_path(['convmem'], convmem)
    bot.memory.save()

def _memory_load(bot):
    if bot.memory.exists(['convmem']):
        convs = bot.memory.get_by_path(['convmem'])
        for convid in convs:
            convmem[convid] = convs[convid]
            if "users" not in convmem[convid]:
                convmem[convid]["users"] = [] # prevent KeyError later


def dumpconv(bot, event, *args):
    """dump all conversations known to the bot"""
    text_search = " ".join(args)
    lines = []
    for convid, convdata in utils._conversation_list_cache.items():
        if text_search.lower() in convdata["title"].lower():
            lines.append("{} <em>{}</em> {}<br />... <b>{}</b>".format(convid, convdata["source"], len(convdata["users"]), convdata["title"]))
    lines.append("<b><em>Totals: {}/{}</em></b>".format(len(lines), len(convmem)))
    bot.send_message_parsed(event.conv, "<br />".join(lines))
