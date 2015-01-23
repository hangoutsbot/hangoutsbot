import hangups
import re
import importlib

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

class simpleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._flags = {"bold" : False, 
                       "italic" : False,
                       "underline" : False, 
                       "link_target" : None}

        self._link_text = None

    def feed(self, html):
        self._segments = list()
        super().feed(html)
        return self._segments

    def handle_starttag(self, tag, attrs):
        if tag == 'b':
            self._flags["bold"] = True
        elif tag == 'i':
            self._flags["italic"] = True
        elif tag == 'u':
            self._flags["underline"] = True
        elif tag == 'a':
            self._link_text = ""
            for attr in attrs:
                if attr[0] == "href":
                    self._flags["link_target"] = attr[1]
                    break

    def handle_endtag(self, tag):
        if tag == 'b':
            self._flags["bold"] = False
        elif tag == 'i':
            self._flags["italic"] = False
        elif tag == 'u':
            self._flags["underline"] = False
        elif tag == 'a':
            self._segments.append(
              hangups.ChatMessageSegment(
                self._link_text,
                hangups.SegmentType.LINK,
                link_target=self._flags["link_target"],
                is_bold=self._flags["bold"], 
                is_italic=self._flags["italic"], 
                is_underline=self._flags["underline"]))
            self._flags["link_target"] = None
        elif tag == 'br':
            self._segments.append(
              hangups.ChatMessageSegment(
                "\n", 
                hangups.SegmentType.LINE_BREAK))

    def handle_data(self, data):
        if self._flags["link_target"] is not None:
            self._link_text += data 
        else:
            self._segments.append(
              hangups.ChatMessageSegment(
                data, 
                is_bold=self._flags["bold"], 
                is_italic=self._flags["italic"], 
                is_underline=self._flags["underline"], 
                link_target=self._flags["link_target"]))

def simple_parse_to_segments(html):
    html = fix_urls(html)
    parser = simpleHTMLParser()
    return parser.feed(html)

def class_from_name(module_name, class_name):
    """adapted from http://stackoverflow.com/a/13808375"""
    # load the module, will raise ImportError if module cannot be loaded
    m = importlib.import_module(module_name)
    # get the class, will raise AttributeError if class cannot be found
    c = getattr(m, class_name)
    return c

def fix_urls(text):
    """adapted from http://stackoverflow.com/a/1071240"""
    pat_url = re.compile(  r'''
                     (?x)( # verbose identify URLs within text
   (http|https|ftp|gopher) # make sure we find a resource type
                       :// # ...needs to be followed by colon-slash-slash
            (\w+[:.]?){2,} # at least two domain groups, e.g. (gnosis.)(cx)
                      (/?| # could be just the domain name (maybe w/ slash)
                [^ \n\r"]+ # or stuff then space, newline, tab, quote
                    [\w/]) # resource name ends in alphanumeric or slash
       $|(?=[\s\.,>)'"\]]) # EOL or assert: followed by white or clause ending
                         ) # end of match group
                           ''')

    for url in re.findall(pat_url, text):
       if url[0]:
        text = text.replace(url[0], '<a href="%(url)s">%(url)s</a>' % {"url" : url[0]})

    return text
