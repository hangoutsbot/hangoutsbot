import hangups
import plugins
import asyncio

def _initialise(bot):
    plugins.register_admin_command(["toggleharmony"])
    plugins.register_handler(_watch_membership_change, type="membership")

def toggleharmony(bot, event, *args):
    
    # Make sure config entries exist
    if not bot.memory.exists(['antileave']):
        bot.memory.set_by_path(['antileave'], {})
    
    if not bot.memory.exists(['antileave', event.conv_id]):
        
        bot.memory.set_by_path(['antileave', event.conv_id], 1)
        html_text = "harmony mode init'd and set to: true"
        
    else:
        setting_antileave = bot.memory.get_by_path(['antileave', event.conv_id])
        
        print(setting_antileave)
        
        if setting_antileave == 1:
            bot.memory.set_by_path(['antileave', event.conv_id], 0)
            html_text = "harmony mode set to: false"
        else:
            bot.memory.set_by_path(['antileave', event.conv_id], 1)
            html_text = "harmony mode set to: true"
    
    bot.send_message_parsed(event.conv, html_text)

@asyncio.coroutine
def _watch_membership_change(bot, event, command):
    
    if event.conv_event.type_ == hangups.MembershipChangeType.LEAVE:
        
        if not bot.memory.exists(['antileave']):
            bot.memory.set_by_path(['antileave'], {})
        
        if bot.memory.exists(['antileave', event.conv_id]):
            
            setting_antileave = bot.memory.get_by_path(['antileave', event.conv_id])
            
            if setting_antileave == 1:
                try:
                    yield from bot._client.adduser(event.conv_id, [event.user.id_.chat_id])
                    yield from bot.coro_send_message(event.conv, _("<b>No leaving, {}.</b>").format(event.user.full_name))
                except NetworkError:
                    yield from bot.coro_send_message(event.conv, _("<b>I can't re-add, {} :\</b>").format(event.user.full_name))
        
    
