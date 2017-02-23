import logging
import plugins
from oauth2client.service_account import ServiceAccountCredentials
import gspread

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive.file'
]

logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_user_command(["lookup"])

def _read_credentials(filename):
    return ServiceAccountCredentials.from_json_keyfile_name(filename, SCOPE)

def lookup(bot, event, *args):
    """find keywords in a specified spreadsheet"""

    if not bot.get_config_suboption(event.conv_id, 'spreadsheet_enabled'):
        yield from bot.coro_send_message(event.conv, "Spreadsheet function disabled")
        return

    if not bot.get_config_suboption(event.conv_id, 'spreadsheet_url'):
        yield from bot.coro_send_message(event.conv, "Spreadsheet URL not set")
        return
    
    if not bot.get_config_suboption(event.conv_id, 'spreadsheet_credentials_file'):
        yield from bot.coro_send_message(event.conv, "Path to Credential File not set")
        return

    spreadsheet_url = bot.get_config_suboption(event.conv_id, 'spreadsheet_url')
    credentials = _read_credentials(bot.get_config_suboption(event.conv_id, 'spreadsheet_credentials_file'))
    
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(spreadsheet_url)
    
    if not bot.get_config_suboption(event.conv_id, 'spreadsheet_worksheet'):
        sheet = sh.sheet1
    else:
        sheet = sh.worksheet(bot.get_config_suboption(event.conv_id, 'spreadsheet_worksheet'))
    
    keyword = ' '.join(args)
    
    htmlmessage = 'Results for keyword <b>{}</b>:<br />'.format(keyword)
    yield from bot.coro_send_message(event.conv, htmlmessage)
    logger.debug("{0} ({1}) has requested to lookup '{2}'".format(event.user.full_name, event.user.id_.chat_id, keyword))
    
    header = sheet.row_values(1)

    while header and header[-1] is '':
        header.pop()
    
    found = sheet.findall(keyword)
    nfounds = len(found)
    
    for c in found:
        foundrow = sheet.row_values(c.row)
        while foundrow and foundrow[-1] is '':
            foundrow.pop()
        result = "{}\n".format(foundrow)

    counter_max = 'temp'
    htmlmessage += '<br />{0} rows found. Only returning first {1}.'.format(nfounds, counter_max)
    
    yield from bot.coro_send_message(event.conv, htmlmessage)
