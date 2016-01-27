import asyncio, logging, urllib

import goslate

from textblob import TextBlob

import plugins


logger = logging.getLogger(__name__)


gs = goslate.Goslate()


def _initialise():
    plugins.register_handler(_handle_message)


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
    logger.info('"{}" to {}'.format(text, iso_language))

    try:
        en_blob = TextBlob(text)
        translated = "{0}".format(en_blob.translate(to=iso_language))
        yield from bot.coro_send_message(event.conv, "<i>" + text_language + "</i> : " + translated)

    except urllib.error.HTTPError as e:
        yield from bot.coro_send_message(event.conv, _("Translation server error: <i>{}</i>").format(str(e)))
        logger.exception(e)
