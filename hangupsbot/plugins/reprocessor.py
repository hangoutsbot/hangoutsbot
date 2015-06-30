import hangups

import plugins

import uuid


_reprocessors = {}

prefix = "uuid://"

def _initialise(bot):
    plugins.register_user_command(["testcontext"])
    plugins.register_handler(_scan_for_reprocessor_context, type="allmessages")
    plugins.register_shared('reprocessor.attach_reprocessor', _attach_reprocessor)


def _attach_reprocessor(func):
    _id = str(uuid.uuid4())
    _reprocessors[_id] = func
    context_fragment = '<a href="' + prefix + _id + '"> </a>'
    return context_fragment


def _scan_for_reprocessor_context(bot, event, command):
    if len(event.conv_event.segments) > 0:
        last_segment = event.conv_event.segments[-1]
        if last_segment.link_target:
            if last_segment.link_target.startswith(prefix):
                _id = last_segment.link_target[len(prefix):]
                if _id in _reprocessors:
                    print("valid uuid: {}".format(_id))
                    event.conv_event.segments.pop()
                    _reprocessors[_id](bot, event, _id)
                    del _reprocessors[_id]


def testcontext(bot, event, *args):
    bot.send_message_parsed(event.conv_id, "This message has hidden context" + bot.call_shared("reprocessor.attach_reprocessor", _reprocess_the_event))

def _reprocess_the_event(bot, event, id):
    bot.send_message_parsed(event.conv_id, '<em>I am responding to a message with uuid: {}</em><br />VISIBLE CONTENT WAS: "{}"'.format(id, event.text))