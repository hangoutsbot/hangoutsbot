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
    credentials = _read_credentials(bot.get_config_suboption(event.conv_id, 'spreadsheet_credentials_file'))
    
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(spreadsheet_url)
    
    if not bot.get_config_suboption(event.conv_id, 'spreadsheet_worksheet'):
        sheet = sh.sheet1
    else:
        sheet = sh.worksheet(bot.get_config_suboption(event.conv_id, 'spreadsheet_worksheet'))
    
    keyword = ' '.join(args)
    
    htmlmessage = _('Results for keyword <b>{}</b>:<br />'.format(keyword))
    logger.debug("{0} ({1}) has requested to lookup '{2}'".format(event.user.full_name, event.user.id_.chat_id, keyword))
    
    header = sheet.row_values(1)
    nheader = len(header)

    while header and header[-1] is '':
        header.pop()
        
    header_word_len = len(''.join(header))
    
    x = 1
    header_string = '| '
    header_word_len = (header_word_len + 2)
    for identifier in header:
        if x == 1:
            pass
        if x < nheader:
            header_string += '{} | '.format(identifier)
            header_word_len = (header_word_len + 3)
        if x == header:
            header_string += '{} |'.format(identifier)
            header_word_len = (header_word_len + 2)
    
    found = sheet.findall(keyword)
    nfounds = len(found)
    
    counter_max = 'temp'
    htmlmessage += _('<br />{0} rows found. Only returning first {1}.'.format(nfounds, counter_max))
    #Currently not working as - is shorter than other chars in HO
    #htmlmessage += '<br />{0}'.format(_repeat_to_length('-', header_word_len))
    htmlmessage += '<br />{0}'.format(header_string)
    
    for c in found:
        foundrow = sheet.row_values(c.row)
        while foundrow and foundrow[-1] is '':
            foundrow.pop()
            
        y = 1
        found_string = '| '
        nfoundrow = len(foundrow)
        
        for identifier in foundrow:
            if x == 1:
                pass
            if y < nfoundrow:
                found_string += '{} | '.format(identifier)
            if y == nfoundrow:
                found_string += '{} |'.format(identifier)
                
        htmlmessage += '<br />{0}'.format(found_string)
    
    yield from bot.coro_send_message(event.conv, htmlmessage)
