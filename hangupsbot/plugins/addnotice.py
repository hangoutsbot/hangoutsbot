import asyncio
import hangups
import plugins

def _initialise(bot):
    plugins.register_handler(_send_notice_to_chat_when_added, type="membership")

@asyncio.coroutine
def _send_notice_to_chat_when_added(bot, event, command):
    message=bot.get_config_option("add_notice_message")
    bot_id = bot._user_list._self_user.id_
    if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        if bot_id in event.conv_event.participant_ids:
            # bot was part of the event
            initiator_user_id = event.user_id.chat_id
            yield from bot.coro_send_message(event.conv,message,context={ "parser": True })
