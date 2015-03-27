import shlex

import hangups

from hangupsbot.handlers import handler, StopEventHandling
from hangupsbot.commands import command


bot_command = "/bot"


@handler.register(priority=5, event=hangups.ChatMessageEvent)
def handle_command(bot, event):
    """Handle command messages"""
    # Test if message starts with bot command keyword
    if not event.text or event.text.split()[0].lower() != bot_command:
        return

    # Test if command handling is enabled
    if not bot.get_config_suboption(event.conv_id, 'commands_enabled'):
        raise StopEventHandling

    # Parse message
    line_args = shlex.split(event.text, posix=False)

    # Test if command length is sufficient
    if len(line_args) < 2:
        bot.send_message(event.conv,
                         _('{}: How may I serve you?').format(event.user.full_name))
        raise StopEventHandling

    # Test if user has permissions for running command
    commands_admin_list = bot.get_config_suboption(event.conv_id, 'commands_admin')
    if commands_admin_list and line_args[1].lower() in commands_admin_list:
        admins_list = bot.get_config_suboption(event.conv_id, 'admins')
        if event.user_id.chat_id not in admins_list:
            bot.send_message(event.conv,
                             _('{}: I\'m sorry, Dave. I\'m afraid I can\'t do that.').format(event.user.full_name))
            raise StopEventHandling

    # Run command
    yield from command.run(bot, event, *line_args[1:])

    # Prevent other handlers from processing event
    raise StopEventHandling
