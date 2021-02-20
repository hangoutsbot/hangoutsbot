import requests
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
from bs4.element import Comment
import logging

import plugins

logger = logging.getLogger(__name__)
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
_internal = {}


def _initialise(bot):
    dev_key = bot.get_config_option("google-customsearch-devkey")
    _internal["cx"] = bot.get_config_option("google-customsearch-cx")
    if dev_key and _internal["cx"]:
        _internal["service"] = build(
            "customsearch", "v1", developerKey=dev_key)
        plugins.register_user_command(["s", "g", "r"])
    else:
        _internal["service"] = None
        logger.error(
            'GOOGLE_SEARCH: config["google-customsearch-devkey"] and config["google-customsearch-cx"] required')


def s(bot, event, *args):
    """ search for a term in google """
    term = " ".join(args)
    if not term or not _internal["service"]:
        return
    exclude_from = ["study.com", "imdb.com", "netflix.com", "khanacademy.org",
                    "www.udemy.com", "github.com", "facebook.com", "en.wikipedia.org",
                    "youtube.com", "twitter.com", "linkedin.com", "www.edx.org", "www.slideshare.net"]
    try:
        html_text = ''
        service = _internal["service"]
        res = service.cse().list(
            q=term,
            cx=_internal["cx"],
        ).execute()
        result = []
        item_len = len(res["items"])
        i = 0
        while(item_len > 0):
            displaylink = res["items"][i]["displayLink"]
            if not any(displaylink.find(site) > -1 for site in exclude_from) and not "fileFormat" in res["items"][i]:
                site_name = res["items"][i]["displayLink"]
                title = res["items"][i]["htmlTitle"]
                link = res["items"][i]["link"]
                result.append(
                    {"site": site_name, "title": title, "link": link})
            i += 1
            if i == item_len or len(result) == 7:
                break
        for idx, item in enumerate(result):
            source = _(
                '<i>{}: <a href="{}">{}</a></i>').format(item["title"], item["link"], item["link"])
            html_text += '{}. <i>{}<br />{}<br />'.format(
                idx + 1, item["site"], source)
        if len(result) == 0:
            html_text = _("<i>no results found for {}</i>").format(term)
        else:
            bot.user_memory_set(event.user.id_.chat_id,
                                'google_search_result', result)
    except Exception as e:
        exception_text = str(e).strip().replace("\n", "<br />")
        html_text = "<i>{}</i>".format(exception_text)
    yield from bot.coro_send_message(event.conv, html_text)


def g(bot, event, *args):
    """get page content from result"""
    term = " ".join(args)
    result = bot.user_memory_get(
        event.user.id_.chat_id, 'google_search_result')
    if not term or not result:
        return
    try:
        link_id = int(term) - 1
        if link_id <= len(result):
            link = result[link_id]["link"]
            """ get text contents of a page """
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
            response = requests.get(link, headers=headers)
            soup = BeautifulSoup(response.content, 'html.parser')
            texts = soup.findAll(text=True)
            visible_texts = filter(tag_visible, texts)
            full_text = u" ".join(t.strip() for t in visible_texts)
            till_comment = full_text.split("comments:", 1)[0]
            till_copyright = till_comment.split("©", 1)[0]
            html_text = till_copyright
        else:
            html_text = _(
                "<i>no results found at index {}</i>").format(link_id + 1)
    except ValueError:
        html_text = "<i>Enter a valid index number</i>"
    except Exception as e:
        exception_text = str(e).strip().replace("\n", "<br />")
        html_text = "<i>{}</i>".format(exception_text)
    yield from bot.coro_send_message(event.conv, html_text)


def r(bot, event, *args):
    """show search result"""
    result = bot.user_memory_get(
        event.user.id_.chat_id, 'google_search_result')
    html_text = ''
    if not result:
        return
    for idx, item in enumerate(result):
        source = _(
            '<i>{}: <a href="{}">{}</a></i>').format(item["title"], item["link"], item["link"])
        html_text += '{}. <i>{}<br />{}<br />'.format(
            idx + 1, item["site"], source)
    yield from bot.coro_send_message(event.conv, html_text)


def tag_visible(element):
    """skip unnecessary tags"""
    if element.parent.name in ['style', 'script', 'head', 'title', 'meta', '[document]']:
        return False
    if isinstance(element, Comment):
        return False
    return True
