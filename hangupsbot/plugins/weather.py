import logging
import plugins
import requests

logger = logging.getLogger(__name__)
_internal = {}

def _initialize(bot):
    api_key = bot.get_config_option('forecast_api_key')
    if api_key:
        _internal['forecast_api_key'] = api_key
        plugins.register_user_command(['weather'])
    else:
        logger.error('WEATHER: config["forecast_api_key"] required')

def weather(bot, event, *args):
    """Returns weather information from Forecast.io.

    (Requires an API key)

    <b>/bot weather <location></b> Get location's current weather.

    <b>/bot weather</b> Get current weather of last used location.
    """
    parameters = list(args)

    if not bot.memory.exists(['weather']):
        bot.memory.set_by_path(['weather'], {})

    if not bot.memory.exists(['weather', event.conv_id]):
        bot.memory.set_by_path(['weather', event.conv_id], {})

    conv_weather = bot.memory.get_by_path(['weather', event.conv_id])

    if not parameters:
        coords = conv_weather.get(event.user_id, None)
        if coords:
            weather = lookup_weather(coords)
            if weather:
                conv_weather[event.user_id] = coords
                yield from bot.coro_send_message(event.conv_id, format_current_weather(weather))
            else:
                yield from bot.coro_send_message(event.conv_id, '<em>Unable to parse forecast data.</em>')
        else:
            yield from bot.coro_send_message(event.conv_id, _('<em>No location history found. Look up weather using /bot weather <b>address</b>.</em>'))
    else:
        if len(parameters) == 1:
            address = parameters[0]
        else:
            address = ''.join(parameters)
        coords = lookup_address(address)
        if coords:
            weather = lookup_weather(coords)
            if weather:
                conv_weather[event.user_id] = coords
                yield from bot.coro_send_message(event.conv_id, format_current_weather(weather))
            else:
                yield from bot.coro_send_message(event.conv_id, '<em>Unable to parse forecast data.</em>')
        else:
            yield from bot.coro_send_message(event.conv_id, _('<em>Location not found: <b>%s</b>.</em>' % (parameters[0])))
        

def format_current_weather(weather):
    """
    Formats the current weather message to the user.
    :params weather: dictionary containing parsed forecast.
    :returns: message to the user.
    """
    return '<em>It is currently %i%s %s, %i%% humidity.</em>' % (weather['temperature'],
                                                                 weather['unit'],
                                                                 weather['summary'],
                                                                 weather['humidity'])

def lookup_address(location):
    """
    Retrieve the coordinates of the location.

    :params location: string argument passed by user.
    :returns: dictionary containing latitutde and longitude.
    """
    google_map_url = 'http://maps.googleapis.com/maps/api/geocode/json'
    payload = {'address': location.replace(' ', '')}
    r = requests.get(google_map_url, params=payload)

    try:
        coords = r.json()['results'][0]['geometry']['location']
    except:
        coords = {}

    return coords

def lookup_weather(coords):
    """
    Retrieve the current forecast at the coordinates.

    :params coords: dictionary containing latitude and longitude.
    :returns: dictionary containing parsed current forecast.
    """

    forecast_io_url = 'https://api.forecast.io/forecast/' + _internal['forecast_api_key'] + '/'
    forecast_io_url += '%s,%s' %  (coords['lat'], coords['lng'])
    logger.info('Forecast.io GET %s' % (forecast_io_url))
    r = requests.get(forecast_io_url)
    logger.info('Request status code: %i' % (r.status_code))

    try:
        j = r.json()['currently']
        current = {
            'temperature': j['temperature'],
            'unit': 'F',
            'humidity': int(j['humidity']*100),
            'summary': j['summary']
        }
    except:
        current = dict()

    return current
