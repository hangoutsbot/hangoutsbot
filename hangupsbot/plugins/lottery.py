import asyncio,re

from random import shuffle

draw_lists = {}

def _initalise(command):
    command.register_handler(_handle_me_action)


@asyncio.coroutine
def _handle_me_action(bot, event, command):
    # perform a simple check for a recognised pattern (/me draw...)
    #   do more complex checking later
    if event.text.startswith('/me draw'):
        yield from command.run(bot, event, *["perform_drawing"])


def prepare(bot, event, *args):
    """prepares a bundle of things for a random draw
        /bot prepare numbers 1-8
            "numbers" = [1,2,3,4,5,6,7,8]
        /bot prepare numbers 42,74,98,3
            "numbers" = [42,74,98,3]
        /bot prepare sticks 3long1short
            "stick" = [long,long,long,short]
        /bot prepare 1-3
            "default" = [1,2,3]

        note: see /me draw for user lottery/drawings

        XXX: generated lists are NOT saved on bot termination
    """
    listname = "default"
    listdef = args[0]
    if len(args) == 2:
        listname = args[0]
        listdef = args[1]
    global_draw_name = event.conv.id_ + "-" + listname

    draw_lists[global_draw_name] = {"box": [], "users": {}}

    """special types
        /bot prepare [thing] COMPASS - 4 cardinal + 4 ordinal

        XXX: add more useful shortcuts here!
    """
    if listdef == "COMPASS":
        listdef = "north,north-east,east,south-east,south,south-west,west,north-west"

    # parse listdef

    if "," in listdef:
        # comma-separated single tokens
        draw_lists[global_draw_name]["box"] = listdef.split(",")

    elif re.match("\d+-\d+", listdef):
        # sequential range: <integer> to <integer>
        _range = listdef.split("-")
        min = int(_range[0])
        max = int(_range[1])
        if min == max:
            raise Exception("prepare: min and max are the same ({})".format(min))
        if max < min:
            min, max = max, min
        max = max + 1 # inclusive
        draw_lists[global_draw_name]["box"] = list(range(min, max))

    else:
        # numberTokens: <integer><name>
        pattern = re.compile("((\d+)([a-z\-_]+))", re.IGNORECASE)
        matches = pattern.findall(listdef)
        if len(matches) > 1:
            for tokendef in matches:
                tcount = int(tokendef[1])
                tname = tokendef[2]
                for i in range(0, tcount):
                    draw_lists[global_draw_name]["box"].append(tname)

        else:
            raise Exception("prepare: unrecognised match (!csv, !range, !numberToken): {}".format(listdef))

    if len(draw_lists[global_draw_name]["box"]) > 0:
        shuffle(draw_lists[global_draw_name]["box"])
        bot.send_message_parsed(
            event.conv,
            "The <b>{}</b> lottery is ready: {} items loaded and shuffled into the box.".format(listname, len(draw_lists[global_draw_name]["box"])))
    else:
        raise Exception("prepare: {} was initialised empty".format(global_draw_name))


def perform_drawing(bot, event, *args):
    """draw handling:
        /me draw[s] [a[n]] number[s] => draws from "number", "numbers" or "numberes"
        /me draw[s] [a[n]] sticks[s] => draws from "stick", "sticks" or "stickses"
        /me draws[s]<unrecognised> => draws from "default"

        note: to prepare lotteries/drawings, see /bot prepare ...

        XXX: check is for singular, plural "-s" and plural "-es"
    """
    pattern = re.compile("/me draws?( +(a +|an +)?([a-z0-9\-_]+))?$", re.IGNORECASE)
    if pattern.match(event.text):
        listname = "default"

        matches = pattern.search(event.text)
        groups = matches.groups()
        if groups[2] is not None:
            listname = groups[2]

        # XXX: TOTALLY WRONG way to handle english plurals!
        # motivation: botmins prepare "THINGS" for a drawing, but users draw a (single) "THING"
        if listname.endswith("s"):
            _plurality = (listname[:-1], listname, listname + "es")
        else:
            _plurality = (listname, listname + "s", listname + "es")
        # seek a matching draw name based on the hacky english singular-plural spellings
        global_draw_name = None
        _test_name = None
        for word in _plurality:
            _test_name = event.conv.id_ + "-" + word
            if _test_name in draw_lists:
                global_draw_name = _test_name
                break

        if global_draw_name is not None:
            if len(draw_lists[global_draw_name]["box"]) > 0:
                if event.user.id_.chat_id in draw_lists[global_draw_name]["users"]:
                    # user already drew something from the box
                    bot.send_message_parsed(event.conv,
                        "<b>{}</b>, you have already drew <b>{}</b> from the <b>{}</b> box".format(
                            event.user.full_name,
                            draw_lists[global_draw_name]["users"][event.user.id_.chat_id],
                            word))

                else:
                    # draw something for the user
                    _thing = str(draw_lists[global_draw_name]["box"].pop())

                    text_drawn = "<b>{}</b> draws <b>{}</b> from the <b>{}</b> box. ".format(event.user.full_name, _thing, word, );
                    if len(draw_lists[global_draw_name]["box"]) == 0:
                        text_drawn = text_drawn + "...AAAAAND its all gone! The <b>{}</b> lottery is over folks.".format(word)

                    bot.send_message_parsed(event.conv, text_drawn)

                    draw_lists[global_draw_name]["users"][event.user.id_.chat_id] = _thing
            else:
                text_finished = "<b>{}</b>, the <b>{}</b> lottery is over. ".format(event.user.full_name, word);

                if event.user.id_.chat_id in draw_lists[global_draw_name]["users"]:
                    text_finished = "You drew a {} previously.".format(draw_lists[global_draw_name]["users"][event.user.id_.chat_id]);

                bot.send_message_parsed(event.conv, text_finished)