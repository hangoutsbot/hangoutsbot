def _initialise(Handlers, bot=None):
    if "register_admin_command" in dir(Handlers) and "register_user_command" in dir(Handlers):
        Handlers.register_admin_command(["attachsyncout", "detachsyncout"])
        return []
    else:
        print(_("SYNCROOMS_CONFIG: LEGACY FRAMEWORK MODE"))
        return ["attachsyncout", "detachsyncout"]


def attachsyncout(bot, event, *args):
    """attach conversations to a new/existing syncout group.
    supply list of conversation ids to attach. supplying an id that is not the current conversation
    will make the bot attempt to attach the current conversation to the specified id. if the id
    does not already exist in another syncout group, a new syncout will be created consisting of
    the current conversation and the specified id. if more than conversation id is supplied, the
    bot will attempt to attach all the conversation ids to an existing syncout provided at least
    one of the supplied ids is in an existing syncout. if all the conversation ids are new, then
    a new syncout will be created. append "quietly" to silently create/attach.
    """

    conversation_ids = list(args)

    quietly = False
    if "quietly" in conversation_ids:
        quietly = True
        conversation_ids.remove("quietly")

    if len(args) == 1:
        conversation_ids.append(event.conv_id)

    conversation_ids = list(set(conversation_ids))

    if len(conversation_ids) < 2:
        # need at least 2 ids, one has to be another room
        return

    if not bot.get_config_option('syncing_enabled'):
        return

    syncouts = bot.get_config_option('sync_rooms')

    if type(syncouts) is not list:
        syncouts = []

    affected_conversations = None

    found_existing = False
    for sync_room_list in syncouts:
        if any(x in conversation_ids for x in sync_room_list):
            missing_ids = list(set(conversation_ids) - set(sync_room_list))
            sync_room_list.extend(missing_ids)
            affected_conversations = list(sync_room_list) # clone
            found_existing = True
            break

    if not found_existing:
        syncouts.append(conversation_ids)
        affected_conversations = conversation_ids

    if affected_conversations:
        bot.config.set_by_path(["sync_rooms"], syncouts)
        bot.config.save()
        if found_existing:
            print(_("SYNCROOM_CONFIG: extended"))
            html_message = _("<i>syncout updated: {} conversations</i>")
        else:
            print(_("SYNCROOM_CONFIG: created"))
            html_message = _("<i>syncout created: {} conversations</i>")
    else:
        print(_("SYNCROOM_CONFIG: no change"))
        html_message = _("<i>syncouts unchanged</i>")

    if not quietly:
        bot.send_message_parsed(event.conv, html_message.format(
            len(affected_conversations)))


def detachsyncout(bot, event, target_conversation_id=None, *args):
    """detach current conversation from a syncout if no parameters supplied. if a conversation id
    is supplied, the bot will attempt to detach that conversation from an existing syncout
    """

    if not bot.get_config_option('syncing_enabled'):
        return

    syncouts = bot.get_config_option('sync_rooms')

    if not syncouts:
        return

    if target_conversation_id is None:
        # detach myself if no target_conversation_id provided
        target_conversation_id = event.conv_id

    _detached = False
    for sync_room_list in syncouts:
        if target_conversation_id in sync_room_list:
            sync_room_list.remove(target_conversation_id)
            _detached = True
            break;

    # cleanup: remove empty or 1-item syncouts by rewriting variable
    _syncouts = []
    for sync_room_list in syncouts:
        if len(sync_room_list) > 1:
            _syncouts.append(sync_room_list)
    syncouts = _syncouts

    if _detached:
        bot.config.set_by_path(["sync_rooms"], syncouts)
        bot.config.save()
        bot.send_message_parsed(event.conv, _("<i>{} was detached</b></i>").format(target_conversation_id))
