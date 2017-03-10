import plugins

def _initialise(bot):
    plugins.register_handler(_check_for_image, type="allmessages")
    plugins.register_user_command(["album"])

def _check_for_image(bot, event, command):
    try:
        a = event.conv_event._event.chat_message.message_content.attachment[0]
        e = a.embed_item
        album = e.plus_photo.thumbnail.url
        album = album[0:album.index('?')]
        bot.conversation_memory_set(event.conv_id, 'album', album)
    except:
        pass

def album(bot, event, *args):
    album = bot.conversation_memory_get(event.conv_id, 'album') or 'Send an image first'
    yield from bot.coro_send_message(event.conv_id, album)
