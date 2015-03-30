"""
Identify images, upload them to google plus, post in hangouts
"""

import asyncio

import aiohttp
import asyncio
import json
import os
from urllib.parse import urlparse
import time

def _initialise(Handlers, bot=None):
    Handlers.register_handler(_watch_image_link, type="message")
    return ["uploadPhoto"]


@asyncio.coroutine
def _watch_image_link(bot, event, command):
    # Don't handle events caused by the bot himself
    if event.user.is_self:
        return
    if (".jpg" in event.text or "imgur.com" in event.text or ".png" in event.text or ".gif" in event.text or ".gifv" in event.text) and "googleusercontent" not in event.text:
        if("imgur.com" in event.text and ".jpg" not in event.text and ".gif" not in event.text and ".gifv" not in event.text and ".png" not in event.text):
            event.text = event.text + ".gif"
        print(event.conv.id_)
        print("yo yo")

        #This uploads and posts the image as I dont fully undrstand returns/yields/etc.
        photoID = yield from uploadPhoto(event.text)
        print("finaID" + photoID)
        bot.testsendchatmessage(event.conv.id_,photoID)

def uploadPhoto(downloadURL):
    downloadURL = downloadURL.replace(".gifv",".gif")
    epoch_time = int(time.time())
    epoch_time = str(epoch_time)+"000"

    fileName = os.path.basename(urlparse(downloadURL).path)
    r = yield from aiohttp.request('get',downloadURL)
    raw = yield from r.read()

    newFile = open('/home/nylonee/images/'+fileName,'wb')
    newFile.write(raw)

    byteSize = os.path.getsize(newFile.name)

    cookies  =  _load_cookies("/home/nylonee/.local/share/hangupsbot/cookies.json")
    cookies = dict(cookies)
    headers = {'content-type' : "application/x-www-form-urlencoded;charset=utf-8","X-GUploader-Client-Info" : "mechanism=scotty xhr resumable; clientVersion=82480166"}

    #NOTE: ALBUMID NEEDS TO BE MANUALLY CREATED AND PASTED INTO THE ALBUMID FIELD
    data = {"protocolVersion":"0.8","createSessionRequest":{"fields":[{"external":{"name":"file","filename":fileName,"put":{},"size":str(byteSize)}},{"inlined":{"name":"use_upload_size_pref","content":"true","contentType":"text/plain"}},{"inlined":{"name":"title","content":fileName,"contentType":"text/plain"}},{"inlined":{"name":"addtime","content":epoch_time,"contentType":"text/plain"}},{"inlined":{"name":"batchid","content":epoch_time,"contentType":"text/plain"}},{"inlined":{"name":"album_id","content":"5269611846786161329","contentType":"text/plain"}},{"inlined":{"name":"album_abs_position","content":"0","contentType":"text/plain"}},{"inlined":{"name":"client","content":"hangouts","contentType":"text/plain"}}]}}
    r = yield from asyncio.async(aiohttp.request('post','https://docs.google.com/upload/photos/resumable?authuser=0',data=json.dumps(data),headers=headers,cookies=cookies))
    raw = yield from asyncio.async(r.json())

    uploadURL = raw["sessionStatus"]["externalFieldTransfers"][0]["putInfo"]["url"]

    headers = {'content-length' : str(byteSize), 'content-type' : "application/x-www-form-urlencoded;charset=utf-8","X-GUploader-Client-Info" : "mechanism=scotty xhr resumable; clientVersion=82480166"}
    r = yield from asyncio.async(aiohttp.request('post',uploadURL,data=open(newFile.name,'rb').read(),headers=headers,cookies=cookies))

    raw = yield from asyncio.async(r.json())

    photoID = raw["sessionStatus"]["additionalInfo"]["uploader_service.GoogleRupioAdditionalInfo"]["completionInfo"]["customerSpecificInfo"]["photoid"]

    return str(photoID)

def _load_cookies(cookie_filename):
    """Return cookies loaded from file or None on failure."""
    try:
        with open(cookie_filename) as f:
            cookies = json.load(f)
            # TODO: Verify that the saved cookies are still valid and ignore
            # them if they are not.
            print('Using saved auth cookies')
            return cookies
    except (IOError, ValueError):
        print('Failed to load saved auth cookies')
