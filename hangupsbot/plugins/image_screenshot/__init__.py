import os
import io
import time
import re

import selenium
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

import plugins


dcap = dict(DesiredCapabilities.PHANTOMJS)
dcap["phantomjs.page.settings.userAgent"] = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/534.34  "
    "(KHTML, like Gecko) PhantomJS/1.9.7 Safari/534.34"
)

def _initialise(bot):
    plugins.register_user_command(["screenshot"])
    plugins.register_admin_command(["seturl", "clearurl"])

def seturl(bot, event, *args):
    """set url for current converation for the screenshot command. 
    use /bot clearurl to clear the previous url before setting a new one.
    """
    url = bot.conversation_memory_get(event.conv_id, 'url')
    if url is None:
        bot.conversation_memory_set(event.conv_id, 'url', ''.join(args))
        html = "<i><b>{}</b> updated screenshot URL".format(event.user.full_name)
        bot.send_html_to_conversation(event.conv, html)
    else:
        html = "<i><b>{}</b> URL already exists for this conversation!<br /><br />".format(event.user.full_name)
        html += "<i>Clear it first with /bot clearurl before setting a new one."
        bot.send_html_to_conversation(event.conv, html)

def clearurl(bot, event, *args):
    """clear url for current converation for the screenshot command. 
    """
    url = bot.conversation_memory_get(event.conv_id, 'url')
    if url is None:
        html = "<i><b>{}</b> nothing to clear for this conversation".format(event.user.full_name)
        bot.send_html_to_conversation(event.conv, html)
    else:
        bot.conversation_memory_set(event.conv_id, 'url', None)
        html = "<i><b>{}</b> URL cleared for this conversation!<br />".format(event.user.full_name)
        bot.send_html_to_conversation(event.conv, html)

def screenshot(bot, event, *args):
    """get a screenshot of a user provided URL or the default URL of the hangout. 
    """
    if args:
        url = args[0]
    else:
        url = bot.conversation_memory_get(event.conv_id, 'url')
    if url is None:
        html = "<i><b>{}</b> No URL has been set for screenshots and none was provided manually.".format(event.user.full_name)
        bot.send_html_to_conversation(event.conv, html)
    else:
        if not re.match(r'^[a-zA-Z]+://', url):
            url = 'http://' + url

        filename = event.conv_id + "." + str(time.time()) +".png"
        filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), filename)
        print("screenshot(): temporary screenshot in {}".format(filepath))

        try:
            browser = webdriver.PhantomJS(desired_capabilities=dcap,service_log_path=os.path.devnull)
        except selenium.common.exceptions.WebDriverException as e:
            bot.send_html_to_conversation(event.conv, "<i>phantomjs could not be started - is it installed?</i>".format(e))
            return

        browser.set_window_size(1280, 800)
        browser.get(url)
        time.sleep(5)
        browser.save_screenshot(filename)

        # read the resulting file into a byte array
        file_resource = open(filename, 'rb')
        image_data = io.BytesIO(file_resource.read())
        os.remove(filename)

        image_id = yield from bot._client.upload_image(image_data, filename=filename)
        yield from bot._client.sendchatmessage(event.conv.id_, None, image_id=image_id)
