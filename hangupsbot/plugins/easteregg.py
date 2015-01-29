import random, asyncio

def easteregg(bot, event, easteregg, eggcount=1, period=0.5, *args):
    """starts easter egg combos (parameters : egg [number] [period])
       supported easter eggs: ponies , pitchforks , bikeshed , shydino"""
    for i in range(int(eggcount)):
        yield from bot._client.sendeasteregg(event.conv_id, easteregg)
        if int(eggcount) > 1:
            yield from asyncio.sleep(float(period) + random.uniform(-0.1, 0.1))
