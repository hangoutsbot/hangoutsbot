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

tokens = [
    Token('b',          *markdown(r'\*'),     is_bold=True),
    Token('i',          *markdown(r'_'),      is_italic=True),
    Token('pre1',       *markdown(r'`'),      skip=True),
    Token('pre2',       *markdown(r'```'),    skip=True),
]

parser = Parser(tokens)

def render_link(link, label):
    if label in link:
        return link
    else:
        return link + " (" + label + ")"

def convert_slack_links(text):
    text = re.sub(r"<(.*?)\|(.*?)>",  lambda m: render_link(m.group(1), m.group(2)), text)
    return text

def slack_markdown_to_hangouts(text, debug=False):
    # workaround: short-circuit on single char inputs
    # important ones are markdown-related
    if text.strip() in [ "*", "_", "`", "~" ]:
        return "\\" + text.strip()

    # workaround: common pattern *<text>
    lines = text.split("\n")
    nlines = []
    for line in lines:
        if re.match("^\*[^* ]", line) and line.count("*") % 2:
            line = line.replace("*", "* ", 1)
        nlines.append(line)
    text = "\n".join(nlines)

    # workaround: accidental consumption of * in "**test"
    replacement_token = "[2star:" + str(uuid.uuid4()) + "]"
    text = text.replace("**", replacement_token)

    output = ""
    segments = parser.parse(text)
    for segment in [ (segment.text,
                      segment.params) for segment in segments ]:

        if debug: print(segment)

        lspace = ""
        rspace = ""
        markdown = []
        text = segment[0]
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

        definition = segment[1]
        if "is_bold" in definition and definition["is_bold"]:
            markdown.append("**")
        if "is_italic" in definition and definition["is_italic"]:
            markdown.append("_")

        output += lspace
        output += "".join(markdown)
        output += text
        output += "".join(markdown[::-1])
        output += rspace

    return output

if __name__ == '__main__':
    print("***TEST OF SLACK MARKDOWN TO HANGOUTS PARSER")
    print("")

    text = ('Hello *bold* world!\n'
            'You can *try _this_ awesome* [link](www.eff.org).\n'
            '*title*\n'
            '* hello\n'
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
    print(text)
    print("")

    output = slack_markdown_to_hangouts(text, debug=True)
    print("")

    print(output)
    print("")
