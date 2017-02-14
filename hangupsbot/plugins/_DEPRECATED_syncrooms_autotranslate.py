import hangups
import goslate
import logging

from textblob import TextBlob

import plugins

logger = logging.getLogger(__name__)

gs = goslate.Goslate()


def _initialise(bot):
    plugins.register_handler(_translate_message, type="sending")
    plugins.register_admin_command(['roomlanguage'])


def _translate_message(bot, broadcast_list, context):
    if context and "autotranslate" in context:
        _autotranslate = context["autotranslate"]
        origin_language = _get_room_language(bot, _autotranslate["conv_id"])
        for send in broadcast_list:
            target_conversation_id = send[0]
            response = send[1]
            target_language = _get_room_language(bot, target_conversation_id)
            if origin_language != target_language:
                logger.debug("translating {} to {}".format(origin_language, target_language))
                translated = _autotranslate["event_text"]
                try:
                    en_blob = TextBlob(_autotranslate["event_text"])
                    translated = "{0}".format(en_blob.translate(to=target_language))
                    #translated = gs.translate(_autotranslate["event_text"], target_language
                except Exception:
                    logger.debug("Translation Api returned string unchanged")
                else:
                    pass
                finally:
                    if _autotranslate["event_text"] != translated:
                    # mutate the original response by reference
                        response.extend([
                            hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK),
                            hangups.ChatMessageSegment('(' + translated + ')')])
    

def _get_room_language(bot, conversation_id, default="en"):
    syncroom_language = bot.conversation_memory_get(conversation_id, 'syncroom_language')
    if syncroom_language is None:
        return default
    else:
        return syncroom_language


def roomlanguage(bot, event, *args):
    """sets the current room language
    supply parameter as either ISO639-1 2-letter language code or fulltext/fragment of language
    to set (e.g. "chinese", "hebr", "swahili", etc).
    """

    language_map = gs.get_languages()

    language = " ".join(args)

    if not language:
        try:
            yield from bot.coro_send_message(
                event.conv,
                _('<i>syncroom "{}" language is {}</i>').format(
                    bot.conversations.get_name(event.conv),
                    language_map[_get_room_language(bot, event.conv_id)]))
        except KeyError:
            pass
        return

    for iso_language in language_map:
        text_language = language_map[iso_language]
        if language.lower() in text_language.lower() or language == iso_language.upper():
            bot.conversation_memory_set(event.conv_id, 'syncroom_language', iso_language)
            yield from bot.coro_send_message(
                event.conv,
                _('<i>syncroom "{}" language set to {}</i>').format(
                    bot.conversations.get_name(event.conv),
                    text_language))
            break
