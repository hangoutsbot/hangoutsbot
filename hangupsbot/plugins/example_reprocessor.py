import hangups

import plugins

def _initialise(bot):
    plugins.register_admin_command(["testcontext"])

def testcontext(bot, event, *args):
    """test hidden context"""
    bot.send_message_parsed(event.conv_id, "This message has hidden context" + bot.call_shared("reprocessor.attach_reprocessor", _reprocess_the_event))

def _reprocess_the_event(bot, event, id):
    bot.send_message_parsed(event.conv_id, '<em>I am responding to a message with uuid: {}</em><br />VISIBLE CONTENT WAS: "{}"'.format(id, event.text))