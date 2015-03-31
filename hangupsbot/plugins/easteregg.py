import random, asyncio


def _initialise(Handlers, bot=None):
    if "register_admin_command" in dir(Handlers) and "register_user_command" in dir(Handlers):
        Handlers.register_admin_command(["easteregg"])
        return []
    else:
        print(_("EASTEREGG: LEGACY FRAMEWORK MODE"))
        return ["easteregg"]


def easteregg(bot, event, easteregg, eggcount=1, period=0.5, *args):
    """starts hangouts easter egg combos.
    supply three parameters: easter egg trigger name, number of times, period (in seconds).
    supported easter egg trigger name: ponies , pitchforks , bikeshed , shydino
    """

    for i in range(int(eggcount)):
        yield from bot._client.sendeasteregg(event.conv_id, easteregg)
        if int(eggcount) > 1:
            yield from asyncio.sleep(float(period) + random.uniform(-0.1, 0.1))
