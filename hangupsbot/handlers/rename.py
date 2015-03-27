import hangups

from hangupsbot.handlers import handler


@handler.register(priority=5, event=hangups.RenameEvent)
def handle_rename(bot, event):
    """Handle conversation rename"""
    # Test if watching for conversation rename is enabled
    if not bot.get_config_suboption(event.conv_id, 'rename_watching_enabled'):
        return

    # Only print renames for now...
    if event.conv_event.new_name == '':
        print(_('{} cleared the conversation name').format(event.user.first_name))
    else:
        print(_('{} renamed the conversation to {}').format(event.user.first_name, event.conv_event.new_name))
