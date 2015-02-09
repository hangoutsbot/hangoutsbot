import goslate
import asyncio

gs = goslate.Goslate()

def _initialise(command):
    command.register_handler(_handle_message)

@asyncio.coroutine
def _handle_message(bot, event, command):
    language_map = {
        "chinese": "zh",
        "german": "de",
        "arabic": "ar",
        "malay": "ms",
        "french": "fr",
        "hindi": "hi",
        "indonesian": "id",
        "tamil": "ta",
        "russian": "ru",
        "ukrainian": "uk",
        "thai": "th",
        "swahili": "sw",
        "japanese": "ja",
        "italian": "it",
        "sinhala": "si",
        "english": "en",
        "esperanto": "eo",
        "turkmen": "tk",
        "tatar": "tt",
        "vietnamese": "vi",
        "hebrew": "he",
        "dutch": "ni",
        "latin": "la",
        "yiddish": "yi",
        "zulu": "zu",
        "welsh": "cy",
    }
    for language_token in language_map:
        language_marker = "/" + language_token
        if language_marker in event.text:
            iso_language = language_map[language_token]
            bare_text = event.text.replace(language_marker, "").strip()

            yield from _translate(bot, event, bare_text, iso_language, language_token)

@asyncio.coroutine
def _translate(bot, event, text, iso_language, text_language):
    translated = gs.translate(text, iso_language)
    bot.send_message_parsed(event.conv, text_language + ": " + translated)
