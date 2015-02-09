import goslate
import asyncio

gs = goslate.Goslate()

def _initialise(command):
    command.register_handler(_handle_message)

@asyncio.coroutine
def _handle_message(bot, event, command):
    language_map = gs.get_languages()
    raw_text = event.text.lower()
    translate_target = None

    for iso_language in language_map:
        text_language = language_map[iso_language].lower()

        language_marker = "/" + text_language
        if language_marker in raw_text:
            raw_text = raw_text.replace(language_marker, "").strip()
            translate_target = [iso_language, text_language]

    yield from _translate(bot, event, raw_text, translate_target[0], translate_target[1])

@asyncio.coroutine
def _translate(bot, event, text, iso_language, text_language):
    translated = gs.translate(text, iso_language)
    bot.send_message_parsed(event.conv, text_language + ": " + translated)
