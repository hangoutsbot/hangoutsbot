#
# Uses the Urbandictionary API
# Shows only the "top" definition as determined by UrbanDictionary.com
# Author: Julian Grammer - dioscuri59@bedsresist.uk
# Version: 2008-Sep-13 09:26
#

import logging, json, plugins, re, requests

logger = logging.getLogger(__name__)
_internal = {}

def _initialize(bot):
		plugins.register_user_command(['urbandict'])

def urbandict(bot, event, *args):

	"""
	<br/><b>lookup a term at UrbanDictionary.com</b>
	<br/>Definitions are from http://www.urbandictionary.com - Don't come crying to me if you find the results offensive!.
	<br/>/bot urbandict <i>word|phrase</i>
	"""
	
	if args:
		searchResult = _lookup_urbandict(bot, event, args)
		if searchResult:
			text = _format_urbandict(searchResult)
		else:
			text = "I can't find a definition of that at www.urbandictionary.com"
	else:
		text = "No word or phrase to search for"
	yield from bot.coro_send_message(event.conv_id, text)
		
def _format_urbandict(data):

	resultStrings = []	
	if ('word' in data):
		resultStrings.append("<br/><b>\"{}\"</b>". format(data['word']))
	if ('definition' in data):
		resultStrings.append("<b>definition:</b> {}".format(re.sub('\[|\]','',data['definition'])))
	if ('example' in data):
		resultStrings.append("<b>example:</b> {}".format(re.sub('\[|\]','',data['example'])))

	return "<br/><br/>".join(resultStrings)
	
def _lookup_urbandict(bot, event, args):

	searchRequest = " ".join(args)
	r = {}
	url = "https://api.urbandictionary.com/v0/define"
	payload = {'term': searchRequest}
	response = requests.get(url, params=payload)
	try:
		results = response.json()['list'][0]
		if 'word' in results:
			r['word'] = results['word']
		if 'definition' in results:
			r['definition'] = results['definition']
		if 'example' in results:
			r['example'] = results['example']

	except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError, requests.exceptions.Timeout):
		logger.error('URBANDICT: {} - {}'.format(response.status_code, response.text))
		return None
	except (ValueError, IndexError) as e:
		logger.error("URBANDICT: {}".format(e))
		return None
	return r
