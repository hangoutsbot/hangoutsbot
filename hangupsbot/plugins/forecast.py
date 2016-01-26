"""
Use forecast.io to get current weather forecast for a given location.

Instructions:
    * Get an API key from https://developer.forecast.io/
    * Store API key in config.json:forecast_api_key
"""

import logging
import requests

import plugins

logger = logging.getLogger(__name__)
_internal = {}

def _initialize(bot):
    api_key = bot.get_config_option('forecast_api_key')
    if api_key:
        _internal['forecast_api_key'] = api_key
        plugins.register_user_command(['forecast'])
    else:
        logger.info('not enabled, need forecast.io API key in config["forecast_api_key"]')


def forecast(bot, event, *args):
    """Returns weather information from Forecast.io.
<b>/bot forecast <location></b> Get location's current weather.
<b>/bot forecast</b> Get current weather of last used location.
<b>/bot forecast unit <F|C></b> Set unit to display degrees."""

    if not bot.memory.exists(['forecast']):
        bot.memory.set_by_path(['forecast'], {})

    if not bot.memory.exists(['forecast', event.conv_id]):
        bot.memory.set_by_path(['forecast', event.conv_id], {})

    conv_forecast = bot.memory.get_by_path(['forecast', event.conv_id])

    unit = conv_forecast.get('unit', 'F')
    _internal['unit'] = unit

    # just setting units
    if len(args) == 2 and args[0] == 'unit':
        unit = parse_unit(args[1])
        if unit is None:
            yield from bot.coro_send_message(
                event.conv_id,
                _('<em>{} is not a recognized unit. Try <b>F</b> or <b>C</b>').format(args[1]))
        else:
            _internal['unit'] = unit
            conv_forecast['unit'] = unit
            bot.memory.set_by_path(['forecast', 'unit'], conv_forecast)
            bot.memory.save()
            yield from bot.coro_send_message(
                event.conv_id,
                _('<em>Reporting weather in degrees {}</em>').format(unit))
        return

    if args:
        coords = lookup_address(' '.join(args))
        if not coords:
            yield from bot.coro_send_message(
                event.conv_id,
                _('<em><b>{}</b>: not found</em>').format(' '.join(args)))
            return
        conv_forecast[event.user.id_.chat_id] = coords
        bot.memory.set_by_path(['forecast', event.conv_id], conv_forecast)
        bot.memory.save()
    else:
        coords = conv_forecast.get(event.user.id_.chat_id, None)
        if not coords:
            yield from bot.coro_send_message(
                event.conv_id,
                _('<em>Your location history not found. Use /bot weather <b>address</b>.</em>'))
            return
    yield from bot.coro_send_message(event.conv_id, lookup_weather(coords))


def lookup_address(location):
    """
    Retrieve the coordinates of the location.

    :params location: string argument passed by user.
    :returns: dictionary containing latitutde and longitude.
    """
    google_map_url = 'https://maps.googleapis.com/maps/api/geocode/json'
    payload = {'address': location}
    resp = requests.get(google_map_url, params=payload)
    try:
        resp.raise_for_status()
        results = resp.json()['results'][0]
        return {
            'lat': results['geometry']['location']['lat'],
            'lng': results['geometry']['location']['lng'],
            'address': results['formatted_address']
        }
    except (IndexError, KeyError):
        logger.error('unable to parse address return data: %d: %s', resp.status_code, resp.json())
        return None


def lookup_weather(coords):
    """
    Retrieve the current forecast at the coordinates.

    :param coords: Dictionary containing latitude and longitude.
    :returns: Dictionary containing parsed current forecast.
    """

    url = 'https://api.forecast.io/forecast/{}/{},{}'.format(
        _internal['forecast_api_key'], coords['lat'], coords['lng'])
    resp = requests.get(url)

    try:
        resp.raise_for_status()
        j = resp.json()['currently']
    except (IndexError, KeyError):
        logger.exception('bad weather results: %d', resp.status_code)
        return _('<em>Unable to parse forecast data.</em>')

    unit = _internal.get('unit', 'F')
    temperature = j['temperature'] if unit == 'F' else to_celsius(j['temperature'])

    return _('<em>In {}, it is currently {}, {:.0f}{} and {:.0f}% humidity.</em>').format(
        coords['address'], j['summary'].lower(), round(temperature, 0), unit, j['humidity']*100)


def to_celsius(f_temp):
    """
    Converts Fahrenheit to Celsius.

    :param f_temp: Temperature in degrees Fahrenheit.
    :returns: Temperature in degrees Celsius.
    """
    return (f_temp - 32) / 1.8


def parse_unit(unit):
    """
    Parses and normalizes user-passed unit of temperature.

    :param unit: User-passed unit of temperature.
    :returns: Normalized unit of temperature.
    """
    if unit.lower() in ['f', 'fahrenheit']:
        return 'F'
    elif unit.lower() in ['c', 'celsius', 'centigrade']:
        return 'C'
    else:
        return None
