"""
Gets current weather forecast for a given location.

Instructions:
    * Get an API key from https://developer.forecast.io/
    * Store API key in config.json:forecast_api_key
"""

import logging
import plugins
import requests

logger = logging.getLogger(__name__)
_internal = {}

def _initialize(bot):
    api_key = bot.get_config_option('forecast_api_key')
    if api_key:
        _internal['forecast_api_key'] = api_key
        plugins.register_user_command(['forecast'])
    else:
        logger.error('FORECAST: config["forecast_api_key"] required')

def forecast(bot, event, *args):
    """Returns weather information from Forecast.io.

    (Requires an API key)

    <b>/bot forecast <location></b> Get location's current weather.

    <b>/bot forecast</b> Get current weather of last used location.

    <b>/bot forecast unit <unit></b> Set unit to display degrees.
    """
    parameters = list(args)

    if not bot.memory.exists(['forecast']):
        bot.memory.set_by_path(['forecast'], {})

    if not bot.memory.exists(['forecast', event.conv_id]):
        bot.memory.set_by_path(['forecast', event.conv_id], {})

    conv_forecast = bot.memory.get_by_path(['forecast', event.conv_id])
    
    unit = conv_forecast.get('unit', 'F')
    _internal['unit'] = unit

    if not parameters:
        coords = conv_forecast.get(event.user.id_.chat_id, None)
        if coords:
            weather = lookup_weather(coords)
            if weather:
                yield from bot.coro_send_message(event.conv_id, format_current_weather(weather))
            else:
                yield from bot.coro_send_message(event.conv_id, '<em>Unable to parse forecast data.</em>')
        else:
            yield from bot.coro_send_message(event.conv_id, _('<em>No location history found. Look up weather using /bot weather <b>address</b>.</em>'))
    else:
        if len(parameters) == 2 and parameters[0] == 'unit':
            unit = parse_unit(parameters[1])
            if unit is None:
                yield from bot.coro_send_message(event.conv_id, ('<em>{} is not '
                                                 'a recognized unit. Try <b>F</b> '
                                                 'or '
                                                 '<b>C</b>').format(parameters[1]))
            else:
                _internal['unit'] = unit
                conv_forecast['unit'] = unit
                bot.memory.set_by_path(['forecast', 'unit'], conv_forecast)
                yield from bot.coro_send_message(event.conv_id, '<em>Reporting weather in degrees {}</em>'.format(unit))

        else:
            if len(parameters) == 1:
                address = parameters[0]
            else:
                address = ''.join(parameters)
            coords = lookup_address(address)
            if coords:
                weather = lookup_weather(coords)
                if weather:
                    conv_forecast[event.user.id_.chat_id] = coords
                    bot.memory.set_by_path(['forecast', event.conv_id], conv_forecast)
                    yield from bot.coro_send_message(event.conv_id, format_current_weather(weather))
                else:
                    yield from bot.coro_send_message(event.conv_id, '<em>Unable to parse forecast data.</em>')
            else:
                yield from bot.coro_send_message(event.conv_id, _(('<em>Location not '
                                                                  'found: '
                                                                  '<b>{}</b>.</em>').format(parameters[0])))

    bot.memory.save()

def format_current_weather(weather):
    """
    Formats the current weather message to the user.

    :param weather: dictionary containing parsed forecast.
    :returns: message to the user.
    """
    return '<em>It is currently {0}{1} {2}, {3}% humidity.</em>'.format(weather['temperature'],
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
    payload = {'address': location}
#    payload = {'address': location.replace(' ', '')}
    r = requests.get(google_map_url, params=payload)

    try:
        coords = r.json()['results'][0]['geometry']['location']
    except:
        coords = {}

    return coords

def lookup_weather(coords):
    """
    Retrieve the current forecast at the coordinates.

    :param coords: Dictionary containing latitude and longitude.
    :returns: Dictionary containing parsed current forecast.
    """

    forecast_io_url = 'https://api.forecast.io/forecast/' + _internal['forecast_api_key'] + '/'
    forecast_io_url += '{},{}'.format(coords['lat'], coords['lng'])
    logger.info('Forecast.io GET {}'.format(forecast_io_url))
    r = requests.get(forecast_io_url)
    logger.info('Request status code: {}'.format(r.status_code))

    try:
        j = r.json()['currently']
        unit = _internal.get('unit', 'F')
        temperature = j['temperature'] if unit == 'F' else to_celsius(j['temperature'])
        temperature = round(temperature, 0)

        current = {
            'temperature': temperature,
            'unit': unit,
            'humidity': int(j['humidity']*100),
            'summary': j['summary']
        }
    except:
        current = dict()

    return current

def to_celsius(f_temp):
    """
    Converts Fahrenheit to Celsius.

    :param f_temp: Temperature in degrees Fahrenheit.
    :returns: Temperature in degrees Celsius.
    """
    return (f_temp - 32) * (5.0/9.0)

def parse_unit(unit):
    """
    Parses and normalizes user-passed unit of temperature.

    :param unit: User-passed unit of temperature.
    :returns: Normalized unit of temperature.
    """
    unit = unit.lower()
    if unit in ['f', 'fahrenheit']:
        return 'F'
    elif unit in ['c', 'celsius', 'centigrade']:
        return 'C'
    else:
        return None
