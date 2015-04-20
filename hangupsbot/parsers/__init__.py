"""file imported by utils.py
more parsers and parser utility functions can be imported here
"""
import hangups

from parsers.kludgy_html_parser import segment_to_html

def simple_parse_to_segments(formatted_text):
    """send formatted chat message
    legacy notice: identical function in kludgy_html_parser
    the older function is "overridden" here for compatibility reasons
    """
    if "message_parser" in dir(hangups):
        # hangups 201504200224 (ae59c24) - uses ReParser
        # supports html, markdown
        segments = hangups.ChatMessageSegment.from_str(formatted_text)
    else:
        # fallback to internal parser on hangups pre-201504200224
        # supports html
        segments = parsers.kludgy_html_parser.simple_parse_to_segments(formatted_text)
    return segments