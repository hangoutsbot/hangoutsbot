"""extremely hacky implementation of html parsing
execute parser test by running this file directly with the interpreter
"""

import logging
import html

from html.parser import HTMLParser

import hangups

import hangups_shim


def simple_parse_to_segments(html, debug=False, **kwargs):
    html = fix_urls(html)
    html = '<html>' + html + '</html>' # html.parser seems to ignore the final entityref without html closure
    parser = simpleHTMLParser(debug)
    return parser.feed(html)


def segment_to_html(segment):
    """Create simple HTML from ChatMessageSegment"""
    text = html.escape(segment.text) if segment.text else ""
    text = text.replace('\n', '<br>\n')

    message = []
    if segment.type_ == hangups_shim.schemas.SegmentType.TEXT:
        message.append(text)
    elif segment.type_ == hangups_shim.schemas.SegmentType.LINK:
        message.append(
            '<a href="{}">{}</a>'.format(segment.link_target if segment.link_target else text, text)
        )
    elif segment.type_ == hangups_shim.schemas.SegmentType.LINE_BREAK:
        message.append('<br />\n')
    else:
        logging.warning('Ignoring unknown chat message segment type: {}'.format(segment.type_))

    if not segment.type_ == hangups_shim.schemas.SegmentType.LINE_BREAK:
        for is_f, f in ((segment.is_bold, 'b'), (segment.is_italic, 'i'),
                        (segment.is_strikethrough, 's'), (segment.is_underline, 'u')):
            if is_f:
                message.insert(0, '<{}>'.format(f))
                message.append('</{}>'.format(f))

    return ''.join(message)


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
                    previous_segment.link_target != self._flags["link_target"] or
                    previous_segment.text == "\n"):
                self.segments_extend(text, type, forceNew=True)
            else:
                previous_segment.text += text

def fix_urls(text):
    tokens = text.split() # "a  b" => (a,b)
    urlified = []
    for token in tokens:
        pretoken = ""
        posttoken = ""
        # consume a token looking for a url-like pattern...
        while len(token)>10: # stop below shortest possible domain http://g.cn length
            if token.startswith(("http://", "https://")):
                break;
            if token[0:1] in ('"', '=', "'", "<"):
                # stop if any consumed character matches possible tag fragment
                break
            pretoken = pretoken + token[0:1]
            token = token[1:]
        if token.startswith(("http://", "https://")):
            _i = 0
            for c in token:
                if c in (")", ">", "]", "!", "*", "<"):
                    posttoken = token[_i:]
                    token = token[0:_i]
                    break
                _i = _i + 1
            token = '<a href="' + token + '">' + token + '</a>'
        token = pretoken + token + posttoken
        urlified.append(token)
    text = " ".join(urlified)
    return text

def test_parser():
    test_strings = [
        ["hello world",
            'hello world', # expected return by fix_urls()
            [1]], # expected number of segments returned by simple_parse_to_segments()
        ["http://www.google.com/",
            '<a href="http://www.google.com/">http://www.google.com/</a>',
            [1]],
        ["https://www.google.com/?a=b&c=d&e=f",
            '<a href="https://www.google.com/?a=b&c=d&e=f">https://www.google.com/?a=b&c=d&e=f</a>',
            [1]],
        ["&lt;html-encoded test&gt;",
            '&lt;html-encoded test&gt;',
            [1]],
        ["A&B&C&D&E",
            'A&B&C&D&E',
            [1]],
        ["A&<b>B</b>&C&D&E",
            'A&<b>B</b>&C&D&E',
            [3]],
        ["A&amp;B&amp;C&amp;D&amp;E",
            'A&amp;B&amp;C&amp;D&amp;E',
            [1]],
        ["C&L",
            'C&L',
            [1]],
        ["<in a fake tag>",
            '<in a fake tag>',
            [1]],
        ['<img src="http://i.imgur.com/E3gxs.gif"/>',
            '<img src="http://i.imgur.com/E3gxs.gif"/>',
            [1]],
        ['<img src="http://i.imgur.com/E3gxs.gif" />',
            '<img src="http://i.imgur.com/E3gxs.gif" />',
            [1]],
        ['<img src="http://i.imgur.com/E3gxs.gif" abc />',
            '<img src="http://i.imgur.com/E3gxs.gif" abc />',
            [1]],
        ['<in "a"="abc" fake tag>',
            '<in "a"="abc" fake tag>',
            [1]],
        ['<in a=abc fake tag>',
            '<in a=abc fake tag>',
            [1]],
        ["abc <some@email.com>",
            'abc <some@email.com>',
            [1]],
        ['</in "a"="xyz" fake tag>', # XXX: fails due to HTMLParser limitations
            '</in "a"="xyz" fake tag>',
            [1]],
        ['<html><html><b></html></b><b>ABC</b>', # XXX: </html> is consumed
            '<html><html><b></html></b><b>ABC</b>',
            [2]],
        ["go here: http://www.google.com/",
            'go here: <a href="http://www.google.com/">http://www.google.com/</a>',
            [2]],
        ['go here: <a href="http://google.com/">http://www.google.com/</a>',
            'go here: <a href="http://google.com/">http://www.google.com/</a>',
            [2]],
        ["go here: http://www.google.com/ abc",
            'go here: <a href="http://www.google.com/">http://www.google.com/</a> abc',
            [3]],
        ['http://i.imgur.com/E3gxs.gif',
            '<a href="http://i.imgur.com/E3gxs.gif">http://i.imgur.com/E3gxs.gif</a>',
            [1]],
        ['(http://i.imgur.com/E3gxs.gif)',
            '(<a href="http://i.imgur.com/E3gxs.gif">http://i.imgur.com/E3gxs.gif</a>)',
            [3]],
        ['(http://i.imgur.com/E3gxs.gif).',
            '(<a href="http://i.imgur.com/E3gxs.gif">http://i.imgur.com/E3gxs.gif</a>).',
            [3]],
        ['XXXXXXXXXXXXXXXXXXXhttp://i.imgur.com/E3gxs.gif)........',
            'XXXXXXXXXXXXXXXXXXX<a href="http://i.imgur.com/E3gxs.gif">http://i.imgur.com/E3gxs.gif</a>)........',
            [3]],
        ["https://www.google.com<br />",
            '<a href="https://www.google.com">https://www.google.com</a><br />',
            [2]]
    ]

    print("*** TEST: utils.fix_urls() ***")
    DEVIATION = False
    for test in test_strings:
        original = test[0]
        expected_urlified = test[1]
        actual_urlified = fix_urls(original)

        if actual_urlified != expected_urlified:
            print("ORIGINAL: {}".format(original))
            print("EXPECTED: {}".format(expected_urlified))
            print(" RESULTS: {}".format(actual_urlified))
            print()
            DEVIATION = True
    if DEVIATION is False:
        print("*** TEST: utils.fix_urls(): PASS ***")

    if DEVIATION is False:
        print("*** TEST: simple_parse_to_segments() ***")
        for test in test_strings:
            original = test[0]
            expected_segment_count = test[2][0]

            segments = simple_parse_to_segments(original)
            actual_segment_count = len(segments)

            if expected_segment_count != actual_segment_count:
                print("ORIGINAL: {}".format(original))
                print("EXPECTED/ACTUAL COUNT: {}/{}".format(expected_segment_count, actual_segment_count))
                for segment in segments:
                    is_bold = 0
                    is_link = 0
                    if segment.is_bold: is_bold = 1
                    if segment.link_target: is_link = 1
                    print(" B L TXT: {} {} {}".format(is_bold, is_link, segment.text))
                print()
                DEVIATION = True
    if DEVIATION is False:
        print("*** TEST: simple_parse_to_segments(): PASS ***")

if __name__ == '__main__':
    test_parser()
