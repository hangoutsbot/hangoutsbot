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
    """Rolls dice
    supply the number and sides of the dice as '<b>n</b>d<b>s</b>' to roll <b>n</b> dice with <b>s</b> sides
    'd<b>s</b>' will roll 1 <b>s</b> sided dice
    no parameters defaults to 1d6
    """
    usage = "usage: diceroll <b>n</b>d<b>s</b>"
    try:
        n,s = dice.split('d')
    except ValueError:
        yield from bot.coro_send_message(event.conv, usage)
        return
    if not s:
        yield from bot.coro_send_message(event.conv, usage)
        return
    if not n:
        n = 1
    n = int(n)
    s = int(s)
    if n < 1:
        yield from bot.coro_send_message(event.conv, "number of dice must be 1 or more")
        return
    if s < 2:
        yield from bot.coro_send_message(event.conv, "number of sides must be 2 or more")
        return
    msg = _("<i>{} rolled ").format(event.user.full_name)
    total = 0
    for i in range(0,n):
        roll = randint(1,s)
        total = total + roll
        if i != 0:
            msg = msg + ", "
        msg = msg + _("<b>{}</b>").format(roll)
    if n != 1:
        msg = msg + _(" totalling <b>{}</b></i>").format(total)
    yield from bot.coro_send_message(event.conv, msg)


def coinflip(bot, event, *args):
    """flip a coin"""
    if randint(1,2) == 1:
        yield from bot.coro_send_message(event.conv, _("<i>{}, coin turned up <b>heads</b></i>").format(event.user.full_name))
    else:
        yield from bot.coro_send_message(event.conv, _("<i>{}, coin turned up <b>tails</b></i>").format(event.user.full_name))
