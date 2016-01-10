# Testing
# when test calls testing(), yield from prohibits execution

import plugins, re, geocoder
from math import sin, cos, sqrt, atan2, radians, asin

def _initialise(bot):
    plugins.register_user_command(["testing", "test"])
    return []

def testing(bot,event,*args):
	# Return the distance between two links
	message = event.text.lower()

	#split on spaces
	spacesplit = message.split(" ")
	coords = []

	#cycle through each piece of the split to determine if geocode
	#	start with pll existence and pull after pll then split at ,
	#	if no pll, then take numbers and split at ,
	#	dump these to a location array
	for tempV in spacesplit:
		pll=re.search("pll=(-?[0-9]+\.[0-9]+,-?[0-9]+\.[0-9]+)",tempV)
		latlongexist=re.search("(-?[0-9]+\.[0-9]+,-?[0-9]+\.[0-9]+)",tempV)
		if pll:
			coords.append(pll.group(1))
		elif latlongexist:
			coords.append(latlongexist.group(1))

	lata = radians(float(coords[0].split(",")[0]))
	lona = radians(float(coords[0].split(",")[1]))

	lat = float(coords[0].split(",")[0])
	lng = float(coords[0].split(",")[1])

	latlng = []
	latlng.append(lat)
	latlng.append(lng)

	g = geocoder.google(latlng, method='reverse')

	origtext = "unknown"

	if g.city_long:
		origtext=g.city_long
	elif g.state_long:
		origtext=g.state_long
	if g.country_long:
		origtext+=", "+g.country_long

#	arraycount = 1
	distlist = []

	for tempV in coords:
		if tempV == coords[0]:
			continue

#		arraycount+=1
		lat = float(tempV.split(",")[0])
		lng = float(tempV.split(",")[1])

		latb = radians(float(tempV.split(",")[0]))
		lonb = radians(float(tempV.split(",")[1]))


		#mad calculations, assuming 6367km earth diameter
		dlon = lonb - lona
		dlat = latb - lata

		a = sin(dlat/2)**2 + cos(lata) * cos(latb) * sin(dlon/2)**2
		c = 2 * asin(sqrt(a))
		km = 6367 * c

		latlng = []
		latlng.append(lat)
		latlng.append(lng)

		g = geocoder.google(latlng, method='reverse')

		text="unknown"
		if g.city_long:
			text=g.city_long
		elif g.state_long:
			text=g.state_long

		if km > 1000:
			if g.country_long:
				text+=", "+g.country_long
		elif km > 200:
			if g.state_long:
				text+=", "+g.state_long
			elif g.country_long:
				text+=", "+g.country_long

		if km > 6881.28:
			text+=" ummm..."
		elif km > 6307:
			text+=" (4 VRLAs)"
		elif km > 1966:
			text+=" (VRLAs)"
		elif km > 655:
			text+=" (LAs)"
		elif km > 400:
			text+=" (2+ agents)"
		elif km > 160:
			text+=" (LAs/2+ agents)"

		distlist.append(_(str(round(km,1))+"km to "+text))
		if km > 6881.28:
			distlist.append(_("    you don't have a snowball's chance in hell"))


	distlist.insert(0, _("<b>Distance(s) from "+origtext+":</b>"))
	result = _("<br/>".join(distlist))

	#print is FYI only, i just learned this is called "tracing"
	print ("testing happens")

	#send message works with "test" but doesn't spit out formatting correctly

	#bot.send_message(event.conv, result)

	yield from bot.coro_send_message(event.conv_id, result)

def test(*args):
	return testing(*args)
