# coding: utf-8

# DownloadURL: http://grammer.net/pubs/src/py/intelloc.py
# Author: dioscuri59@bedsresist.uk

# Version: Wednesday 10 October 2018, 10:08:34

"""
Intelloc - Ingress Intel Map Portal Link Locator

Uses Here.com reverse geocoding to get plain text location from 'pll' lat/lng of intel map portal link.

expects plugins/s2ingress.py to be present
s2ingress can be downloaded from http://grammer.net/pubs/src/py

Instructions:
	* Get an App-ID and App-Code from https://developer.here.com/
	* Store App-ID  in config.json:here_app_id
	* Store App-Code in config.json:here_app_code
"""

import asyncio, logging, plugins, requests, plugins.s2ingress as s2

logger = logging.getLogger(__name__)

hereUrl = 'https://reverse.geocoder.api.here.com/6.2/reversegeocode.json'

_internal = {}

def _initialize(bot):
	here_app_id = bot.get_config_option('here_app_id')
	if here_app_id:
		_internal['here_app_id'] = here_app_id
	else:
		logger.error('INTELLOC: config["here_app_id"] required')
		
	here_app_code = bot.get_config_option('here_app_code')
	if here_app_code:
		_internal['here_app_code'] = here_app_code
	else:
		logger.error('INTELLOC: config["here_app_code"] required')
	
	if here_app_id and here_app_code:
		plugins.register_handler(_watch_messages, type="message")

@asyncio.coroutine
def _watch_messages(bot, event, *args):

	def processMessage(message):
		ll = None
		pll = None
		link = []
		query = []
		coords = []
		splitMess = message.split()
		for s in splitMess:
			if s[:33] == 'https://www.ingress.com/intel?ll=':
				link.append(s)
		if link:
			for l in link:
				query = l.split('?')[1]
				params = query.split('&')
				for s in params:
					logger.debug(s)
					if s[:3] == 'll=':
						ll = s[3:]
					if s[:4] == 'pll=':
						pll = s[4:]
				if pll == None:
					if ll != None:
						pll = ll
						f = False
				else:
					f = True
				coords.append([pll, f, l])
			return coords

	if event.user.is_self:
		return

	coords = processMessage(event.text.lower())
	if coords == None:
		return

	text = '<br/>'
	locs = len(coords)
	word = 'locations'
	if locs == 1:
		word = 'location'
	text += '{} {} found<br/><br/>'.format(locs, word)
	for c in coords:
		text += '{}<br/>'.format(c[2])
	text += '------------------------------<br/>'
	for c in coords:
		pll = c[0]
		f = c[1]
		if not f:
			text += 'Portal lat/lng (pll) missing, using map centre (ll) instead)<br/>'
		gmapsLink = 'https://maps.google.com/?q={}'.format(pll)
		lat = float(pll.split(',')[0])
		lng = float(pll.split(',')[1])
		payload = {'app_id': _internal['here_app_id'], 'app_code': _internal['here_app_code'], 'mode': 'retrieveAddresses', 'maxresults': '1', 'prox': pll, }
		try:
			response = requests.get(hereUrl, params = payload).json()
			address = str(response['Response']['View'][0]['Result'][0]['Location']['Address']['Label'])
			addr = address.split(',')
			address = ''
			for a in addr:
				address += '     {}<br/>'.format(a)
		except:
			text += 'ERROR getting location - Status code {}'.format(str(r.status_code))
			logger.exception(text)
		text += '<br/>Location:<br/>{}<br/>Ingress score region:<br/>     {}<br/><br/>Google Maps link:<br/>     {}<br/>'.format(address, s2.latLngToRegion(lat, lng), gmapsLink)
		if len(coords) > coords.index(c)+1:
			text += '<br/>------------------------------<br/>'
	yield from bot.coro_send_message(event.conv,text)
