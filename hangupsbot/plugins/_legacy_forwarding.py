import asyncio
import hangups

def _initialise(Handlers, bot=None):
    Handlers.register_handler(_handle_legacy_forwarding, type="message")
    return []

@asyncio.coroutine
def _handle_legacy_forwarding(bot, event, command):
    """Handle message forwarding"""
    # Test if message forwarding is enabled
    if not bot.get_config_suboption(event.conv_id, 'forwarding_enabled'):
        return

    forward_to_list = bot.get_config_suboption(event.conv_id, 'forward_to')
    if forward_to_list:
        print(_("FORWARDING: {}").format(forward_to_list))
        for dst in forward_to_list:
            try:
                conv = bot._conv_list.get(dst)
            except KeyError:
                continue

            # Prepend forwarded message with name of sender
            link = 'https://plus.google.com/u/0/{}/about'.format(event.user_id.chat_id)
            segments = [hangups.ChatMessageSegment(event.user.full_name, hangups.SegmentType.LINK,
                                                   link_target=link, is_bold=True),
                        hangups.ChatMessageSegment(': ', is_bold=True)]
            # Copy original message segments
            segments.extend(event.conv_event.segments)
            # Append links to attachments (G+ photos) to forwarded message
            if event.conv_event.attachments:
                segments.append(hangups.ChatMessageSegment('\n', hangups.SegmentType.LINE_BREAK))
                segments.extend([hangups.ChatMessageSegment(link, hangups.SegmentType.LINK, link_target=link)
                                 for link in event.conv_event.attachments])

            bot.send_message_segments(conv, segments)
