import plugins

import hangups


def _initialise(bot):
    plugins.register_handler(on_hangout_call, type="call")


def on_hangout_call(bot, event, command):
    if event.conv_event._event.hangout_event.event_type == hangups.schemas.ClientHangoutEventType.END_HANGOUT:
        bot.send_html_to_conversation(event.conv_id, "<i><b>{}</b>, it's been 0 days since the last call</i>".format(event.user.full_name))

