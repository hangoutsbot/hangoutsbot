import logging


logger = logging.getLogger(__name__)


from html.parser import HTMLParser

class htmlToMarkdownParser(HTMLParser):
    def feed(self, html, basic_markdown={}, debug=False):
        self._markdown = ""
        self._basic = basic_markdown

        self._link_href = False
        self._link_buffer = False

        self.debug = debug

        super().feed(html)

        return self._markdown

    def handle_starttag(self, tag, attrs):
        if self.debug:
            print("start tag: {} {}".format(tag, attrs))

        if tag == "a":
            for attrname, attrval in attrs:
                if attrname == "href":
                    self._link_buffer = "(" + attrval + ")"
                    break
        else:
            self.add_tag(tag, 0)

    def handle_endtag(self, tag):
        if self.debug:
            logger.info("end tag: {}".format(tag))

        if tag == "a":
            self._markdown += self._link_buffer
            self._link_buffer = False
        else:
            self.add_tag(tag, 1)

    def handle_data(self, data):
        if self.debug:
            logger.info("data: {}".format(data))

        if self._link_buffer:
            self._link_buffer = "[" + data + "]" + self._link_buffer
        else:
            self._markdown += data

    def add_tag(self, tag, pos):
        if tag in self._basic:
            if isinstance(self._basic[tag], list):
                self._markdown += self._basic[tag][pos]
            else:
                self._markdown += self._basic[tag]

def html_to_hangups_markdown(html, debug=False):
    parser = htmlToMarkdownParser()
    return parser.feed(
        html,
        {   "b": "**",
            "em": "_",
            "i": "_",
            "pre": "`",
            "code": "`",
            "br": ["", "\n"] },
        debug = debug )


if __name__ == '__main__':
    print("***TEST OF HTML TO HANGUPS MARKDOWN PARSER")
    print("")

    html = ( '<B>THE SYNCROOM TEST</B><br />'
             '<b><a href="https://plus.google.com/u/01234567890/about">'
             'ABCDEFG MNOPQRSTUV</a></b><br />'
             '... (<a href="mailto:ABCD@efghijk.com">ABCD@efghijk.com</a>)<br />'
             '... 01234567890<br /><b>Users: 1</b>' )

    print(html_to_hangups_markdown(html, debug=True))
    print("")
