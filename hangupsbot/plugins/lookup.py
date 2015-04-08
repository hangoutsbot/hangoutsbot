import hangups

def lookup(bot, event, *args):
    """find keywords in a specified spreadsheet"""

    if not bot.get_config_option('spreadsheet_enabled'):
        bot.send_message_parsed(event.conv, _("Spreadsheet function disabled"))
        return

    if not bot.get_config_option('spreadsheet_url'):
        bot.send_message_parsed(event.conv, _("Spreadsheet URL not set"))
        return

    spreadsheet_url = bot.get_config_option('spreadsheet_url')
    table_class = "waffle" # Name of table class to search. Note that 'waffle' seems to be the default for all spreadsheets

    keyword = ' '.join(args)

    htmlmessage = _('Results for keyword <b>{}</b>:<br />').format(keyword)

    print(_("{0} ({1}) has requested to lookup '{2}'").format(event.user.full_name, event.user.id_.chat_id, keyword))
    import urllib.request
    html = urllib.request.urlopen(spreadsheet_url).read()

    keyword_lower = keyword.strip().lower()

    data = []

    counter = 0
    counter_max = 5 # Maximum rows displayed per query

    # Adapted from http://stackoverflow.com/questions/23377533/python-beautifulsoup-parsing-table
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(str(html, 'utf-8'))
    table = soup.find('table', attrs={'class':table_class})
    table_body = table.find('tbody')

    rows = table_body.find_all('tr')

    for row in rows:
        col = row.find_all('td')
        cols = [ele.text.strip() for ele in col]
        data.append([ele for ele in cols if ele]) # Get rid of empty values

    for row in data:
        matchfound = 0
        for cell in row:
            testcell = str(cell).lower().strip()
            if (keyword_lower in testcell) and counter < counter_max and matchfound == 0:
                htmlmessage += _('<br />Row {}: ').format(counter+1)
                for datapoint in row:
                    htmlmessage += '{} | '.format(datapoint)
                htmlmessage += '<br />'
                counter += 1
                matchfound = 1
            elif (keyword_lower in testcell) and counter >= counter_max:
                counter += 1

    if counter > counter_max:
        htmlmessage += _('<br />{0} rows found. Only returning first {1}.').format(counter, counter_max)
    if counter == 0:
        htmlmessage += _('No match found')

    bot.send_html_to_conversation(event.conv, htmlmessage)
