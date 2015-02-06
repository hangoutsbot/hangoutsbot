import hangups
import re
import importlib
import html

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
    def __init__(self, debug=False, **kwargs):
        super().__init__(kwargs)

        self._debug = debug

        self._flags = {"bold" : False, 
                       "italic" : False,
                       "underline" : False, 
                       "link_target" : None}

        self._link_text = None

        self._allow_extra_html_tag = False;

    def feed(self, html):
        self._segments = list()
        super().feed(html)
        return self._segments

    def handle_starttag(self, tag, attrs):
        if tag == 'html':
            if self._allow_extra_html_tag:
                self.segments_extend(self.get_starttag_text(), "starttag")
            else:
                # skip the first <html> tag added by simple_parse_to_segments()
                self._allow_extra_html_tag = True
        elif tag == 'b':
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
        else:
            # preserve the full text of the tag
            self.segments_extend(self.get_starttag_text(), "starttag")

    def handle_startendtag(self, tag, attrs):
        if tag == 'br':
            self.segments_linebreak()
        else:
            # preserve the full text of the tag
            self.segments_extend(self.get_starttag_text(), "startendtag")

    def handle_endtag(self, tag):
        if tag == 'html':
            # XXX: any closing html tag will always go missing!
            pass
        elif tag == 'b':
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
        else:
            # xxx: this removes any attributes inside the tag
            self.segments_extend("</" + tag + ">", "endtag")

    def handle_entityref(self, name):
        if self._flags["link_target"] is not None:
            if(self._debug): print("simpleHTMLParser(): [LINK] entityref {}".format(name))
            self._link_text += "&" + name 
        else:
            _unescaped = html.unescape("&" + name)
            self.segments_extend(_unescaped, "entityref")

    def handle_data(self, data):
        if self._flags["link_target"] is not None:
            if(self._debug): print("simpleHTMLParser(): [LINK] data \"{}\"".format(data))
            self._link_text += data 
        else:
            self.segments_extend(data, "data")

    def segments_linebreak(self):
        self._segments.append(
            hangups.ChatMessageSegment(
                "\n", 
                hangups.SegmentType.LINE_BREAK))

    def segments_extend(self, text, type, forceNew=False):
        if len(self._segments) == 0 or forceNew is True:
            if(self._debug): print("simpleHTMLParser(): [NEW] {} {}".format(type, text))
            self._segments.append(
              hangups.ChatMessageSegment(
                text,
                is_bold=self._flags["bold"], 
                is_italic=self._flags["italic"], 
                is_underline=self._flags["underline"], 
                link_target=self._flags["link_target"]))
        else:
            if(self._debug): print("simpleHTMLParser(): [APPEND] {} {}".format(type, text))
            previous_segment = self._segments[-1]
            if (previous_segment.is_bold != self._flags["bold"] or
                    previous_segment.is_italic != self._flags["italic"] or
                    previous_segment.is_underline != self._flags["underline"] or
                    previous_segment.text == "\n"):
                self.segments_extend(text, type, forceNew=True)
            else:
                previous_segment.text += text

def simple_parse_to_segments(html, debug=False, **kwargs):
    html = fix_urls(html, debug)
    html = '<html>' + html + '</html>' # html.parser seems to ignore the final entityref without html closure
    parser = simpleHTMLParser(debug)
    return parser.feed(html)

def class_from_name(module_name, class_name):
    """adapted from http://stackoverflow.com/a/13808375"""
    # load the module, will raise ImportError if module cannot be loaded
    m = importlib.import_module(module_name)
    # get the class, will raise AttributeError if class cannot be found
    c = getattr(m, class_name)
    return c

def fix_urls(text, debug=False):
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

    if debug: print("fix_urls(): {}".format(text))

    return text

def test_parser():
    print("PARSER TEST")
    test_strings = [
        "hello world",
        "http://www.google.com/",
        "https://www.google.com/?a=b&c=d&e=f",
        "&lt;html-encoded test&gt;",
        "A&B&C&D&E",
        "A&<b>B</b>&C&D&E",
        "A&amp;B&amp;C&amp;D&amp;E",
        "C&L",
        "go here: http://www.google.com/",
        'go here: <a href="http://google.com/">http://www.google.com/</a>',
        "<in a fake tag>",
        '<img src="hello" abc />',
        '<in "a"="abc" fake tag>',
        '<in a=abc fake tag>',
        "abc <some@email.com>",
        '</in "a"="xyz" fake tag>', # XXX: fails due to HTMLParser limitations
        '<html><html><b></html></b><b>ABC</b>', # XXX: </html> is consumed
    ]
    for test in test_strings:
        print("TEST STRING: {}".format(test))
        segments = simple_parse_to_segments(test, debug=True)
        for segment in segments:
            is_bold = 0
            is_link = 0
            if segment.is_bold: is_bold = 1
            if segment.link_target: is_link = 1
            print("segment: {} {} {}".format(is_bold, is_link, segment.text))
        print("-----")

if __name__ == '__main__':
    test_parser()