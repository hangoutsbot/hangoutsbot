from random import randint

def diceroll(bot, event, *args):
    bot.send_message_parsed(event.conv, "<i>{} rolled <b>{}</b></i>".format(event.user.full_name, randint(1,6)))

def coinflip(bot, event, *args):
    if randint(1,2) == 1:
        bot.send_message_parsed(event.conv, "<i>{}, coin turned up <b>heads</b></i>".format(event.user.full_name))
    else:
        bot.send_message_parsed(event.conv, "<i>{}, coin turned up <b>tails</b></i>".format(event.user.full_name))