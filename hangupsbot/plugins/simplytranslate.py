import goslate
import asyncio

gs = goslate.Goslate()

def _initialise(command):
    command.register_handler(_handle_message)

@asyncio.coroutine
def _handle_message(bot, event, command):
    language_map = gs.get_languages()
    raw_text = event.text.lower()
    raw_text = ' '.join(raw_text.split())
    translate_target = None

    for iso_language in language_map:
        text_language = language_map[iso_language].lower()

        language_marker = " /" + text_language
        if raw_text.endswith(language_marker):
            raw_text = raw_text.replace(language_marker, "").strip()
            translate_target = [iso_language, text_language]

    if translate_target is not None:
        yield from _translate(bot, event, raw_text, translate_target[0], translate_target[1])

@asyncio.coroutine
def _translate(bot, event, text, iso_language, text_language):
    print('TRANSLATE: "{}" to {}'.format(text, iso_language))
    translated = gs.translate(text, iso_language)
    bot.send_message_parsed(event.conv, "<i>" + text_language + "</i> : " + translated)
