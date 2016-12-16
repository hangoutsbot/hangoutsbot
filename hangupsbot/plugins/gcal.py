"""
Integration with Google Calendar.

To generate the client secrets file::

    $ python -m plugins.gcal client_id client_secret path/to/secrets.json

Config keys:

    - `gcal.secrets`: path to the generated secrets file
    - `gcal.id`: calendar ID (defaults to `primary`)
"""


from argparse import ArgumentParser
from datetime import date, datetime
from httplib2 import Http
import logging
import shlex

from googleapiclient.discovery import build
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage

import plugins


DATE = "%Y-%m-%d"
DATETIME = "%Y-%m-%dT%H:%M:%SZ"

logger = logging.getLogger(__name__)
config = None
service = None


def _initialise(bot):
    global config, service
    config = bot.get_config_option("gcal")
    if not config or "secrets" not in config:
        logger.error("gcal: missing path to secrets file")
        return
    store = Storage(config["secrets"])
    http = store.get().authorize(Http())
    service = build("calendar", "v3", http=http)
    plugins.register_user_command(["calendar"])

def pretty_date(d):
    now = datetime.utcnow()
    if isinstance(d, datetime):
        diff = d - now
        if diff.seconds < 0:
            return "now"
        elif diff.days == 0:
            if diff.seconds < 60 * 60:
                mins = diff.seconds // 60
                return "in {} minute{}".format(mins, "" if mins == 1 else "s") # in 10 minutes
            else:
                hrs = diff.seconds // (60 * 60)
                return "in {} hour{}".format(hrs, "" if hrs == 1 else "s") # in 3 hours
        elif diff.days == 1:
            return "tomorrow {}".format(d.strftime("%H:%M")) # tomorrow 11:30
        elif diff.days < 7:
            return d.strftime("%A %H:%M") # Monday 11:30
        else:
            return d.strftime("%d/%m/%Y %H:%M") # 19/12/2016 11:30
    elif isinstance(d, date):
        now = now.date()
        diff = d - now
        if diff.days == 0:
            return "today"
        elif diff.days == 1:
            return "tomorrow"
        elif diff.days < 7:
            return d.strftime("%A") # Monday
        else:
            return d.strftime("%d/%m/%Y") # 19/12/2016

def cal_list():
    resp = service.events().list(calendarId=config.get("id", "primary"),
                                 timeMin=date.today().strftime(DATETIME),
                                 singleEvents=True, orderBy="startTime").execute()
    if not resp["items"]:
        return "No upcoming events."
    msg = "Upcoming events:"
    for pos, item in enumerate(resp["items"]):
        if "dateTime" in item["start"]:
            start = datetime.strptime(item["start"]["dateTime"], DATETIME)
        elif "date" in item["start"]:
            start = datetime.strptime(item["start"]["date"], DATE).date()
        msg += "\n{}. <b>{}</b> -- {}".format(pos + 1, item["summary"], pretty_date(start))
        if "description" in item:
            msg += "\n<i>{}</i>".format(item["description"])
        if "location" in item:
            msg += "\n{}".format(item["location"])
    return msg

def cal_add(what, when, where=None, desc=None):
    data = {"summary": what, "start": {}}
    try:
        data["start"]["dateTime"] = datetime.strptime(when, "%d/%m/%Y %H:%M").strftime(DATETIME)
    except ValueError:
        try:
            data["start"]["date"] = datetime.strptime(when, "%d/%m/%Y").strftime(DATE)
        except ValueError:
            return "Couldn't parse the date.  Make sure it's in `dd/mm/yyyy hh:mm` format."
    data["end"] = data["start"]
    if where:
        data["location"] = where
    if desc:
        data["description"] = desc
    service.events().insert(calendarId=config.get("id", "primary"), body=data).execute()
    return "Added <b>{}</b> to the calendar.".format(data["summary"])

def calendar(bot, event, *args):
    args = shlex.split(event.text)[2:] # better handling of quotes
    msg = None
    if not args:
        args = ["list"]
    if args[0] == "help":
        msg = "Usage:\n" \
              "- list events: `/bot calendar list`\n" \
              "- add a new event: `/bot calendar add <what> <when> [where] [description]`"
    elif args[0] == "list":
        msg = cal_list()
    elif args[0] == "add":
        if len(args) < 3:
            msg = "Need to specify both what and when."
        else:
            msg = cal_add(*args[1:5])
    else:
        msg = "Unknown command, try `help` for a list."
    if msg:
        yield from bot.coro_send_message(event.conv_id, msg)


if __name__ == "__main__":

    from oauth2client import tools

    parser = ArgumentParser(parents=[tools.argparser])
    parser.add_argument("client_id", help="public key for Google APIs")
    parser.add_argument("client_secret", help="secret key for Google APIs")
    parser.add_argument("path", help="output file for the generated secrets file")
    args = parser.parse_args()

    flow = OAuth2WebServerFlow(client_id=args.client_id, client_secret=args.client_secret,
                               scope="https://www.googleapis.com/auth/calendar")
    tools.run_flow(flow, Storage(args.path), args)
