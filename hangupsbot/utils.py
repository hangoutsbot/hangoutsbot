import hangups
import re

from html.parser import HTMLParser
from html.entities import name2codepoint

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

def cheap_parse_blocks_to_segments(blocks):
    # receives a string array containing markdown-like syntax
    # e.g. ["'''''bold and italic ",
    #       "'''bold only ",
    #       "[hello world](http://google.com)"]
    # note that the trailing space is required to avoid mashing "blocks" together
    # XXX: needs more work for natural text input
    segments = list()
    for b in blocks:

         """basic formatting"""
         is_bold = False
         is_italic = False
         if b.startswith("'''''"):
             is_bold = True
             is_italic = True
             b = b[5:]
         elif b.startswith("'''"):
             is_bold = True
             b = b[3:]
         elif b.startswith("''"):
             is_italic = True
             b = b[2:]

         """detect line break"""
         break_after = False
         if b.endswith("\n"):
            break_after = True

         b = b.strip("\n")

         """link"""
         link_target = None
         markdown_match = re.search("^\[(.*?)\]\((.*?)\)", b)
         if markdown_match:
             link_target = markdown_match.group(2)
             b = markdown_match.group(1)
         elif b.startswith(("http://", "https://", "//")):
             link_target = b

         segments.append(
           hangups.ChatMessageSegment(
             b, 
             is_bold=is_bold, 
             is_italic=is_italic, 
             link_target=link_target))

         """line break"""
         if break_after:
             segments.append(
               hangups.ChatMessageSegment(
                 "\n", 
                 hangups.SegmentType.LINE_BREAK))

    return segments

class simpleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._flags = {"bold" : False, 
                       "italic" : False,
                       "underline" : False, 
                       "link_target" : None}

    def feed(self, html):
        self._segments = list()
        super().feed(html)
        return self._segments

    def handle_starttag(self, tag, attrs):	
        print("Start tag:", tag)

        if tag == 'b':
            self._flags["bold"] = True
        elif tag == 'i':
            self._flags["italic"] = True
        elif tag == 'u':
            self._flags["underline"] = True
        elif tag == 'a':
            for attr in attrs:
                if attr[0] == "href":
                    self._flags["link_target"] = attr[1]
                    break

    def handle_endtag(self, tag):
        print("End tag  :", tag)

        if tag == 'b':
            self._flags["bold"] = False
        elif tag == 'i':
            self._flags["italic"] = False
        elif tag == 'u':
            self._flags["underline"] = False
        elif tag == 'a':
            self._flags["link_target"] = None
        elif tag == 'br':
            self._segments.append(
              hangups.ChatMessageSegment(
                "\n", 
                hangups.SegmentType.LINE_BREAK))

    def handle_data(self, data):
        print("Data     :", data)
        print(" flags   : {} {} {} {}".format(
                                         self._flags["bold"], 
                                         self._flags["italic"],
                                         self._flags["underline"],
                                         self._flags["link_target"]))
        self._segments.append(
          hangups.ChatMessageSegment(
            data, 
            is_bold=self._flags["bold"], 
            is_italic=self._flags["italic"], 
            is_underline=self._flags["underline"], 
            link_target=self._flags["link_target"]))

def simple_parse_to_segments(html):
    parser = simpleHTMLParser()
    return parser.feed(html)

if __name__ == '__main__':
    parser = simpleHTMLParser()
    print(simple_parse_to_segments('<b><i>abcdefg</i> is before hijk</b><br /><br /><b><a href="abcdef">xyz</a></b>'))

