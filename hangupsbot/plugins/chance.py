import asyncio

from random import randint

import plugins


def _initialise(bot):
    plugins.register_handler(_handle_me_action)
    plugins.register_user_command(["diceroll", "coinflip"])


def _handle_me_action(bot, event, command):
    if event.text.startswith('/me'):
        if event.text.find("roll dice") > -1 or event.text.find("rolls dice") > -1 or event.text.find("rolls a dice") > -1 or event.text.find("rolled a dice") > -1:
            yield from asyncio.sleep(0.2)
            yield from command.run(bot, event, *["diceroll"])
        elif event.text.find("flips a coin") > -1 or event.text.find("flips coin") > -1 or event.text.find("flip coin") > -1 or event.text.find("flipped a coin") > -1:
            yield from asyncio.sleep(0.2)
            yield from command.run(bot, event, *["coinflip"])
        else:
            pass


def diceroll(bot, event, dice="1d6", *args):
    """rolls dice
    supply the number and sides of the dice as 'xdy' to roll x dice with y sides, e.g. 2d10 rolls 2 ten sided dice
    specifying simply dy will roll 1 y sided dice
    no parameter defaults to 1d6
    """
    errmsg = "<i>dice rolls are specified as '$number<b>d</b>$sides'</i>"
    try:
        n,s = dice.split('d')
    except Exception:
        yield from bot.coro_send_message(event.conv, errmsg)
        return
    if not s:
        yield from bot.coro_send_message(event.conv, errmsg)
        return
    if not n:
        n = 1
    msg = "<i>{} rolled <b>".format(event.user.full_name)
    tot = 0
    for i in range(0,int(n)):
        r = randint(1,int(s))
        tot = tot+r
        if i != 0:
            msg = msg+", "
        msg = msg+"{}".format(r)
    if int(n) != 1:
        msg = msg+"</b> for a total of <b>{}</b></i>".format(tot)
    yield from bot.coro_send_message(event.conv, msg)


def coinflip(bot, event, *args):
    """flip a coin"""
    if randint(1,2) == 1:
        yield from bot.coro_send_message(event.conv, _("<i>{}, coin turned up <b>heads</b></i>").format(event.user.full_name))
    else:
        yield from bot.coro_send_message(event.conv, _("<i>{}, coin turned up <b>tails</b></i>").format(event.user.full_name))
