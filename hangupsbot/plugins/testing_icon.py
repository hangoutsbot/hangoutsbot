import hangups

def geticon(bot, event, *args):
    """ Return the avatar of the person who called this command """
    response = yield from bot._client.getentitybyid([event.user_id.chat_id])
    try:
        photo_url = "http:" + response['entity'][0]['properties']['photo_url']
    except Exception as e:
        print("refreshusers() {} {}".format(event.user_id.chat_id, e))

    bot.send_html_to_conversation(event.conv_id, photo_url)
