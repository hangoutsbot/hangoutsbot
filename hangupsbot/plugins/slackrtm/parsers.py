# -*- coding: utf-8 -*-

import re
import uuid

from reparser import Parser, Token, MatchGroup

def markdown(tag):
    """Return sequence of start and end regex patterns for simple Markdown tag"""
    return (markdown_start.format(tag=tag), markdown_end.format(tag=tag))

boundary_chars = r'\s`!\'".,<>?*_~='

b_left = r'(?:(?<=[' + boundary_chars + r'])|(?<=^))'  # Lookbehind
b_right = r'(?:(?=[' + boundary_chars + r'])|(?=$))'   # Lookahead

markdown_start = b_left + r'(?<!\\){tag}(?!\s)(?!{tag})'
markdown_end = r'(?<!{tag})(?<!\s)(?<!\\){tag}' + b_right

tokens_slack_to_hangups = [
    Token('b',          *markdown(r'\*'),     is_bold=True),
    Token('i',          *markdown(r'_'),      is_italic=True),
    Token('pre1',       *markdown(r'`'),      skip=True),
    Token('pre2',       *markdown(r'```'),    skip=True) ]

tokens_hangups_to_slack = [
    Token('b',          *markdown(r'\*\*'),    bold=True) ]

parser_slack_to_hangups = Parser(tokens_slack_to_hangups)
parser_hangups_to_slack = Parser(tokens_hangups_to_slack)

def render_link(link, label):
    if label in link:
        return link
    else:
        return link + " (" + label + ")"

def convert_slack_links(text):
    text = re.sub(r"<(.*?)\|(.*?)>",  lambda m: render_link(m.group(1), m.group(2)), text)
    return text

def slack_markdown_to_hangups(text, debug=False):
    lines = text.split("\n")
    nlines = []
    for line in lines:
        # workaround: for single char lines
        if len(line) < 2:
            line = line.replace("*", "\\*")
            line = line.replace("_", "\\_")
            nlines.append(line)
            continue

        # workaround: common pattern *<text>
        if re.match("^\*[^* ]", line) and line.count("*") % 2:
            line = line.replace("*", "* ", 1)

        # workaround: accidental consumption of * in "**test"
        replacement_token = "[2star:" + str(uuid.uuid4()) + "]"
        line = line.replace("**", replacement_token)

        segments = parser_slack_to_hangups.parse(line)

        nline=""
        for segment in [ (segment.text,
                          segment.params) for segment in segments ]:

            if debug: print(segment)

            text = segment[0]
            definition = segment[1]

            lspace = ""
            rspace = ""
            text = text.replace(replacement_token, "**")
            if text[0:1] == " ":
                lspace = " "
                text = text[1:]
            if text[-1:] == " ":
                rspace = " "
                text = text[:-1]

            # manually escape to prevent hangups markdown processing
            text = text.replace("*", "\\*")
            text = text.replace("_", "\\_")
            text = convert_slack_links(text)

            markdown = []
            if "is_bold" in definition and definition["is_bold"]:
                markdown.append("**")
            if "is_italic" in definition and definition["is_italic"]:
                markdown.append("_")

            nline += lspace
            nline += "".join(markdown)
            nline += text
            nline += "".join(markdown[::-1])
            nline += rspace

        nlines.append(nline)
    text = "\n".join(nlines)
    return text


def hangups_markdown_to_slack(text, debug=False):
    lines = text.split("\n")
    nlines = []
    output = ""
    for line in lines:
        segments = parser_hangups_to_slack.parse(line)
        for segment in [ [segment.text,
                          segment.params] for segment in segments ]:

            if debug: print(segment)

            text = segment[0]
            definition = segment[1]

            # convert links to slack format
            text = re.sub(r"\[(.*?)\]\((.*?)\)", r"<\2|\1>", text)

            wrapper = ""
            if "bold" in definition and definition["bold"]:
                # bold
                wrapper = "*"

            nlines.append(wrapper + text + wrapper)
    output = "\n".join(nlines)
    return output


if __name__ == '__main__':
    print("***SLACK MARKDOWN TO HANGUPS")
    print("")

    text = ('Hello *bold* world!\n'
            'You can *try _this_ awesome* [link](www.eff.org).\n'
            '*title*\n'
            '*hello\n'
            '* world\n'
            '*\n'
            '_\n'
            '*\n'
            '¯\_(ツ)_/¯\n'
            '<http://www.google.com.sg|Google Singapore> <http://www.google.com.my|Google Malaysia>\n'
            '<http://www.google.com|www.google.com>\n'
            'www.google.com\n'
            '**hello\n'
            '*** hi\n'
            '********\n'
            '_ xya kskdks')
    print(repr(text))
    print("")

    output = slack_markdown_to_hangups(text, debug=True)
    print("")

    print(repr(output))
    print("")

    print("***HANGUPS MARKDOWN TO SLACK PARSER")
    print("")

    text = ('**[bot] test markdown**\n'
            '**[ABCDEF ABCDEF](https://plus.google.com/u/0/1234567890/about)**\n'
            '... ([ABC@DEF.GHI](mailto:ABC@DEF.GHI))\n'
            '... 1234567890\n'
            '**[XYZ XYZ](https://plus.google.com/u/0/1234567890/about)**\n'
            '... 0123456789\n'
            '**`_Users: 2_`**' )
    print(repr(text))
    print("")

    output = hangups_markdown_to_slack(text, debug=True)
    print("")

    print(repr(output))
    print("")

