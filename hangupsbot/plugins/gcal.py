"""
Integration with Google Calendar.

To generate the client secrets file::

    $ python -m plugins.gcal client_id client_secret path/to/secrets.json

Then set config key `gcal.secrets` to the path of the newly generated file.
"""


from argparse import ArgumentParser
from datetime import date, datetime
from httplib2 import Http
import logging

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
                return "in {} minutes".format(diff.seconds // 60) # in 10 minutes
            else:
                return "in {} hours".format(diff.seconds // (60 * 60)) # in 3 hours
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

def calendar(bot, event, *args):
    msg = None
    if not args:
        args = ["list"]
    if args[0] == "help":
        msg = "Usage:\n" \
              "- list events: `/bot calendar list`"
    elif args[0] == "list":
        resp = service.events().list(calendarId=config.get("id", "primary"),
                                     timeMin=date.today().strftime(DATETIME)).execute()
        if not resp["items"]:
            msg = "No upcoming events."
        else:
            msg = "Upcoming events:"
            for item in resp["items"]:
                if "dateTime" in item["start"]:
                    start = datetime.strptime(item["start"]["dateTime"], DATETIME)
                elif "date" in item["start"]:
                    start = datetime.strptime(item["start"]["date"], DATE).date()
                msg += "\n<b>{}</b> -- {}".format(item["summary"], pretty_date(start))
                if "description" in item:
                    msg += "\n<i>{}</i>".format(item["description"])
                if "location" in item:
                    msg += "\n{}".format(item["location"])
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
