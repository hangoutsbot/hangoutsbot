"""
simple "ask" function for wolfram alpha data
credit goes to @billius for the original plugin

instructions:
* pip3 install wolframalpha
* get API KEY from http://products.wolframalpha.com/developers/
* put API KEY in config.json:wolframalpha-apikey
"""

import wolframalpha

import plugins


_internal = {}


def _initialise(bot):
    apikey = bot.get_config_option("wolframalpha-apikey")
    if apikey:
        _internal["client"] = wolframalpha.Client(apikey)
        plugins.register_user_command(["ask"])
    else:
        print(_("WOLFRAMALPHA: config.wolframalpha-apikey required"))


def ask(bot, event, *args):
    """request data from wolfram alpha"""

    keyword = ' '.join(args)
    res = _internal["client"].query(keyword)

    html = '<b>"{}"</b><br /><br />'.format(keyword)

    has_content = False
    for pod in res.pods:
        if pod.title:
            html += "<b>{}:</b> ".format(pod.title)

        if pod.text and pod.text.strip():
            html += pod.text.strip().replace("\n", "<br />") + "<br />"
            has_content = True
        else:
            for node in pod.node.iter():
                if node.tag == "img":
                    html += '<a href="' + node.attrib["src"] + '">' + node.attrib["src"] + "</a><br />"
                    has_content = True

    if not has_content:
        html = _("<i>Wolfram Alpha did not return any useful data</i>")

    bot.send_html_to_conversation(event.conv, html)
