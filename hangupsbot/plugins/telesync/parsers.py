# -*- coding: utf-8 -*-

import re

from reparser import Parser, Token, MatchGroup

def markdown(tag):
    """Return sequence of start and end regex patterns for simple Markdown tag"""
    return (markdown_start.format(tag=tag), markdown_end.format(tag=tag))

boundary_chars = r'\s`!\'".,<>?*_~='

b_left = r'(?:(?<=[' + boundary_chars + r'])|(?<=^))'  # Lookbehind
b_right = r'(?:(?=[' + boundary_chars + r'])|(?=$))'   # Lookahead

markdown_start = b_left + r'(?<!\\){tag}(?!\s)(?!{tag})'
markdown_end = r'(?<!{tag})(?<!\s)(?<!\\){tag}' + b_right

tokens = [
    Token('b',          *markdown(r'\*\*'),    bold=True),
    Token('i',          *markdown(r'_'),       italic=True),
    Token('pre',        *markdown(r'`'),       pre=True) ]

parser = Parser(tokens)

def hangups_markdown_to_telegram(text, debug=False):
    lines = text.split("\n")
    nlines = []
    output = ""
    for line in lines:
        single_line = ""

        segments = parser.parse(line)
        for segment in [ [segment.text,
                          segment.params] for segment in segments ]:

            if debug: print(segment)

            text = segment[0]
            definition = segment[1]

            """telegram api markdown does not accept nested markdown"""

            if re.match(r"\[.*?\]\(.*?\)", text):
                # prioritise markdown style links
                definition = {}

            wrapper = ""
            if "pre" in definition and definition["pre"]:
                # pre-formatted
                wrapper = "`"
            elif "bold" in definition and definition["bold"]:
                # bold
                wrapper = "*"
            elif "italic" in definition and definition["italic"]:
                # italics
                wrapper = "_"

            text = text.replace("_", "\\_")

            segment_to_text = wrapper + text + wrapper
            single_line += segment_to_text

        nlines.append(single_line)
    output = "\n".join(nlines)
    return output


if __name__ == '__main__':
    print("***HANGUPS MARKDOWN TO TELEGRAM PARSER")
    print("")
    text = ('**[bot] test markdown**\n'
            '**[ABCDEF ABCDEF](https://plus.google.com/u/0/1234567890/about)**\n'
            '... ([ABC@DEF.GHI](mailto:ABC@DEF.GHI))\n'
            '... 1234567890\n'
            '**[XYZ XYZ](https://plus.google.com/u/0/1234567890/about)**\n'
            '_ x\n'
            '_x\n'
            '... 0123456789\n'
            '**`_Users: 2_`**'
            'You are at **`THE SYNCROOM TEST`**, conv_id = _`Ugx78I99r-mbd_u_jSV4AaABAQ`_' )
    print(repr(text))
    print("")

    output = hangups_markdown_to_telegram(text, debug=True)
    print("")

    print(repr(output))
    print("")
