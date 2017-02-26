import logging
import plugins
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import re

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive.file'
]

logger = logging.getLogger(__name__)


def _initialise(bot):
    plugins.register_user_command(["lookup"])

def _read_credentials(filename):
    return ServiceAccountCredentials.from_json_keyfile_name(filename, SCOPE)

def _repeat_to_length(string_to_expand, length):
    return (string_to_expand * length)

def lookup(bot, event, *args):
    """find keywords in a specified spreadsheet"""

    if not bot.get_config_suboption(event.conv_id, 'spreadsheet_enabled'):
        yield from bot.coro_send_message(event.conv, _("Spreadsheet function disabled"))
        return

    if not bot.get_config_suboption(event.conv_id, 'spreadsheet_url'):
        yield from bot.coro_send_message(event.conv, _("Spreadsheet URL not set"))
        return
    
    if not bot.get_config_suboption(event.conv_id, 'spreadsheet_credentials_file'):
        yield from bot.coro_send_message(event.conv, _("Path to Credential File not set"))
        return

    spreadsheet_url = bot.get_config_suboption(event.conv_id, 'spreadsheet_url')
    if "pubhtml" in spreadsheet_url:
        spreadsheet_id = spreadsheet_url.split('/')[5]
        spreadsheet_url = "https://docs.google.com/spreadsheets/d/{}".format(spreadsheet_id)
        
    credentials = _read_credentials(bot.get_config_suboption(event.conv_id, 'spreadsheet_credentials_file'))
    
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(spreadsheet_url)
    
    if not bot.get_config_suboption(event.conv_id, 'spreadsheet_worksheet'):
        sheet = sh.sheet1
    else:
        sheet = sh.worksheet(bot.get_config_suboption(event.conv_id, 'spreadsheet_worksheet'))
    
    if args[0].startswith('<'):
        counter_max = int(args[0][1:]) # Maximum rows displayed per query
        keyword = ' '.join(args[1:])
    else:
        counter_max = 5
        keyword = ' '.join(args)
    search = re.compile(r'{}'.format(keyword), re.I)
    
    htmlmessage = _('Results for keyword <b>{}</b>:<br />'.format(keyword))
    logger.debug("{0} ({1}) has requested to lookup '{2}'".format(event.user.full_name, event.user.id_.chat_id, keyword))
    
    found = sheet.findall(search)
    nfounds = len(found)
    
    if nfounds == 1:
        htmlmessage += _('<br />1 row found.')
    if nfounds == 0:
        htmlmessage += _('No match found')
    if nfounds > counter_max:
        htmlmessage += _('<br />{0} rows found. Only returning first {1}.').format(nfounds, counter_max)
        if counter_max == 5:
            htmlmessage += _('<br />Hint: Use <b>/bot lookup <{0} {1}</b> to view {0} rows').format(counter_max*2, keyword)
    #Currently not working as - is shorter than other chars in HO
    #htmlmessage += '<br />{0}'.format(_repeat_to_length('-', header_word_len))
    for c in found[:counter_max]:
        foundrow = sheet.row_values(c.row)
        while foundrow and foundrow[-1] is '':
            foundrow.pop()
        
        htmlmessage += _('<br />Row {}: ').format(c.row)
        y = 1
        found_string = '| '
        nfoundrow = len(foundrow)
        
        for identifier in foundrow:
            if y == 1:
                pass
            if y < nfoundrow:
                found_string += '{} | '.format(identifier)
            if y == nfoundrow:
                found_string += '{} |'.format(identifier)

        htmlmessage += '<br />{0}'.format(found_string)
    
    yield from bot.coro_send_message(event.conv, htmlmessage)
