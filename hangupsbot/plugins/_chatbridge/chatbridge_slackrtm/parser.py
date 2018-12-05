from hangups import hangouts_pb2, message_parser, ChatMessageSegment
from reparser import Token, MatchGroup


def tag(start, end=None):
    """
    An extension of the Markdown tags, allows reversing the start and end tags.
    """
    return (message_parser.MARKDOWN_START.format(tag=start),
            message_parser.MARKDOWN_END.format(tag=end or start))


class SlackMessageParser(message_parser.ChatMessageParser):

    # Tokens to parse Slack's "mrkdwn" formatting into hangups segments.
    slack_tokens = [Token("sl_b", *tag(r"\*"), is_bold=True),
                    Token("sl_i", *tag(r"_"), is_italic=True),
                    Token("sl_s", *tag(r"~"), is_strikethrough=True),
                    Token("sl_pre", *tag(r"```"), skip=True),
                    Token("sl_code", *tag(r"`"), skip=True),
                    # Don't use func=message_parser.url_complete here.
                    # We want to preserve Slack-specific targets (e.g. user links).
                    Token("sl_link1", r"<(?P<url>[^>]+?)\|(?P<text>.+?)>",
                          text=MatchGroup("text"), link_target=MatchGroup("url")),
                    Token("sl_link2", r"<(?P<url>.+?)>",
                          text=MatchGroup("url"), link_target=MatchGroup("url"))]

    def __init__(self, from_slack):
        if from_slack:
            # Take the basic token set, add Slack formatting.
            super().__init__(message_parser.Tokens.basic + self.slack_tokens)
        else:
            # Use hangups' standard tokens for HTML and Markdown.
            super().__init__()
        self.bold = "**" if from_slack else "*"
        self.italic = "_"
        self.strike = "~"
        self.from_slack = from_slack

    def convert(self, source, slack):
        if isinstance(source, str):
            # Parse, then convert reparser.Segment to hangups.ChatMessageSegment.
            segments = [ChatMessageSegment(seg.text, **seg.params) for seg in self.parse(source)]
        else:
            # We'll assume it's already a ChatMessageSegment list.
            segments = source
        formatted = ""
        current = []
        for seg in segments:
            if seg.type_ == hangouts_pb2.SEGMENT_TYPE_LINE_BREAK:
                # Insert closing tags for all current formatting, in reverse order.
                for chars in reversed(current):
                    formatted += chars
                # Start a new line.
                formatted += "\n"
                # Now reinsert the current formatting.
                for chars in current:
                    formatted += chars
                continue
            if self.from_slack:
                text = seg.text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
                if seg.link_target:
                    if seg.link_target[0] == "@":
                        # User link, just replace with the plain username.
                        user = seg.link_target[1:]
                        if user in slack.users:
                            user = slack.users[user]["name"]
                        text = "@{}".format(user)
                    elif seg.link_target[0] == "#":
                        # Channel link, just replace with the plain channel name.
                        channel = seg.link_target[1:]
                        if channel in slack.channels:
                            channel = slack.channels[channel]["name"]
                        text = "#{}".format(channel)
                    else:
                        # Markdown link: [label](target)
                        text = "[{}]({})".format(text, message_parser.url_complete(seg.link_target))
            else:
                text = seg.text.replace("&", "&amp;").replace(">", "&gt;").replace("<", "&lt;")
                if seg.link_target:
                    if text == seg.link_target:
                        # Slack implicit link: <target>
                        text = "<{}>".format(seg.link_target)
                    else:
                        # Slack link with label: <target|label>
                        text = "<{}|{}>".format(seg.link_target, text)
            # Compare formatting of the previous segment to the current one.
            formatting = {self.bold: seg.is_bold,
                          self.italic: seg.is_italic,
                          self.strike: seg.is_strikethrough}
            # Insert closing tags for any formatting that ends here.
            # Apply in reverse order to opened tags.
            for chars in reversed(current):
                if not formatting[chars]:
                    formatted += chars
                    current.remove(chars)
            # Insert opening tags for any formatting that starts here.
            for chars, condition in formatting.items():
                if condition and chars not in current:
                    formatted += chars
                    current.append(chars)
            # XXX: May generate tags closed in the wrong order: *bold _bold+italic* italic_
            # Testing suggests both Slack and Hangouts can cope with this though.
            formatted += text
        # Close any remaining format tags.
        formatted += "".join(reversed(current))
        return formatted


from_slack = SlackMessageParser(True)
from_hangups = SlackMessageParser(False)
