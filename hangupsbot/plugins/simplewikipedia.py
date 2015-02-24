import wikipedia
import re

def wiki(bot, event, *args):
    """lookup a term on Wikipedia"""

    term = " ".join(args)
    if not term:
        return

    try:
        page = wikipedia.page(term)

        summary = page.summary.strip()
        summary = summary.replace('\r\n', '\n').replace('\r', '\n')
        summary = re.sub('\n+', "\n", summary).replace('\n', '<br /><br />')
        source = '<i>source: <a href="{}">{}</a></i>'.format(page.url, page.url)

        html_text = '<b>"{}"</b><br /><br />{}<br /><br />{}'.format(term, summary, source)
    except wikipedia.exceptions.PageError:
        html_text = "<i>no entry found for {}</i>".format(term)
    except wikipedia.exceptions.DisambiguationError as e:
        exception_text = str(e).strip().replace("\n", "<br />")
        html_text = "<i>{}</i>".format(exception_text)

    bot.send_message_parsed(event.conv, html_text)


def _initialise(Handlers, bot=None):
    Handlers.register_user_command(["wiki"])
    return []
