import asyncio
import hangups

from random import randint

def _initialise(Handlers, bot=None):
    Handlers.register_handler(_watch_membership_change, type="membership")


@asyncio.coroutine
def _watch_membership_change(bot, event, command):
    # Generate list of added or removed users
    event_users = [event.conv.get_user(user_id) for user_id
                   in event.conv_event.participant_ids]
    names = ', '.join([user.full_name for user in event_users])

    # JOIN
    if event.conv_event.type_ == hangups.MembershipChangeType.JOIN:
        print('{} has added {}'.format(event.user.full_name, names))
    # LEAVE
    else:
        print('{} has left'.format(names))