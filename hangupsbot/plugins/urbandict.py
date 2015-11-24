#
# Simple interface to urbandictionary.com
#
# Author: Roman Bogorodskiy <bogorodskiy@gmail.com>

import sys

from urllib.request import urlopen
from urllib.parse import quote as urlquote
from html.parser import HTMLParser

import plugins


class TermType(object):
    pass


class TermTypeRandom(TermType):
    pass


class UrbanDictParser(HTMLParser):

    def __init__(self, *args, **kwargs):
        HTMLParser.__init__(self, *args, **kwargs)
        self._section = None
        self.translations = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if not tag in ("div", "a"):
            return

        div_class = attrs_dict.get('class')
        if div_class in ('word', 'meaning', 'example'):
            self._section = div_class
            if div_class == 'word':  # NOTE: assume 'word' is the first section
                self.translations.append(
                    {'word': '', 'def': '', 'example': ''})

    def handle_endtag(self, tag):
        if tag == 'div':
            #NOTE: assume there is no nested <div> in the known sections
            self._section = None

    def handle_data(self, data):
        if not self._section:
            return

        if self._section == 'meaning':
            self._section = 'def'
        elif self._section == 'word':
            data = data.strip()

        self.translations[-1][self._section] += normalize_newlines(data)


def normalize_newlines(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


def urbandict(bot, event, *args):
    """lookup a term on Urban Dictionary.
    supplying no parameters will get you a random term.
    DISCLAIMER: all definitions are from http://www.urbandictionary.com/ - the bot and its
    creators/maintainers take no responsibility for any hurt feelings.
    """

    term = " ".join(args)
    if not term:
        url = "http://www.urbandictionary.com/random.php"
    else:
        url = "http://www.urbandictionary.com/define.php?term=%s" % \
              urlquote(term)

    f = urlopen(url)
    data = f.read().decode('utf-8')

    urbanDictParser = UrbanDictParser()
    try:
        urbanDictParser.feed(data)
    except IndexError:
        # apparently, nothing was returned
        pass

    if len(urbanDictParser.translations) > 0:
        html_text = ""
        the_definition = urbanDictParser.translations[0]
        html_text += '<b>"' + the_definition["word"] + '"</b><br /><br />'
        if "def" in the_definition:
            html_text += _("<b>definition:</b> ") + the_definition["def"].strip().replace("\n", "<br />") + '<br /><br />'
        if "example" in the_definition:
            html_text += _("<b>example:</b> ") + the_definition["example"].strip().replace("\n", "<br />")

        yield from bot.coro_send_message(event.conv, html_text)
    else:
        if term:
            yield from bot.coro_send_message(event.conv, _('<i>no urban dictionary definition for "{}"</i>').format(term))
        else:
            yield from bot.coro_send_message(event.conv, _('<i>no term from urban dictionary</i>'))


def _initialise(bot):
    plugins.register_user_command(["urbandict"])
