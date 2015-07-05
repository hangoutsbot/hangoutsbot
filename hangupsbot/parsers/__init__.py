"""file imported by utils.py
more parsers and parser utility functions can be imported here
"""
import hangups

import parsers.kludgy_html_parser

from parsers.kludgy_html_parser import segment_to_html

def simple_parse_to_segments(formatted_text):
    """send formatted chat message
    legacy notice: identical function in kludgy_html_parser
    the older function is "overridden" here for compatibility reasons
    """
    if "message_parser" in dir(hangups):
        # ReParser is available in hangups 201504200224 (ae59c24) onwards
        # supports html, markdown
        segments = hangups.ChatMessageSegment.from_str(formatted_text)
    else:
        # fallback to internal parser
        # supports html
        segments = kludgy_html_parser.simple_parse_to_segments(formatted_text)
    return segments