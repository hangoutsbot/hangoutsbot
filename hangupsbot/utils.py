import importlib
import unicodedata
import sys

import hangups

from parsers import simple_parse_to_segments, segment_to_html

from hangups.ui.utils import get_conv_name as hangups_get_conv_name


_conversation_list_cache = {}


def text_to_segments(text):
    """Create list of message segments from text"""
    # Replace two consecutive spaces with space and non-breakable space,
    # then split text to lines
    lines = text.replace('  ', ' \xa0').splitlines()
    if not lines:
        return []

    # Generate line segments
    segments = []
    for line in lines[:-1]:
        if line:
            segments.append(hangups.ChatMessageSegment(line))
        segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
    if lines[-1]:
        segments.append(hangups.ChatMessageSegment(lines[-1]))

    return segments


def unicode_to_ascii(text):
    """Transliterate unicode characters to ASCII"""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()


def class_from_name(module_name, class_name):
    """adapted from http://stackoverflow.com/a/13808375"""
    # load the module, will raise ImportError if module cannot be loaded
    m = importlib.import_module(module_name)
    # get the class, will raise AttributeError if class cannot be found
    c = getattr(m, class_name)
    return c


def get_conv_name(conv, truncate=False):
    """drop-in replacement for hangups.ui.utils.get_conv_name
    truncate added for backward-compatibility, should be always False
    """
    if isinstance(conv, str):
        convid = conv
    else:
        convid = conv.id_

    try:
        convdata = _conversation_list_cache[convid]
        title = convdata["title"]
    except (KeyError, AttributeError) as e:
        if not isinstance(conv, str):
            title = hangups_get_conv_name(conv, truncate=False)
        else:
            raise ValueError("could not determine conversation name")

    return title


def get_all_conversations():
    return _conversation_list_cache

