import asyncio
import logging
import uuid

from collections import namedtuple

from hangups import ChatMessageEvent

import plugins
import threadmanager

from parsers.markdown import html_to_hangups_markdown

from sinks import aiohttp_start
from sinks.base_bot_request_handler import AsyncRequestHandler as IncomingRequestHandler


logger = logging.getLogger(__name__)

class FakeEvent:
    def __init__(self, text, user, passthru, conv_id=None):
        self.text = text
        self.user = user
        self.passthru = passthru
        self.conv_id = conv_id

FakeUser = namedtuple( 'user', [ 'full_name',
                                 'id_' ])

FakeUserID = namedtuple( 'userID', [ 'chat_id',
                                     'gaia_id' ])


class WebFramework:
    instance_number = 0

    def __init__(self, bot, configkey, RequestHandler=IncomingRequestHandler, extra_metadata={}):
        self.uid = False
        self.plugin_name = False

        self.bot = self._bot = bot
        self.configkey = configkey
        self.RequestHandler = RequestHandler

        self.load_configuration(configkey)

        self.setup_plugin()

        if not self.plugin_name:
            logger.warning("plugin_name not defined in code, not running")
            return

        if not self.uid:
            self.uid = "{}-{}".format(self.plugin_name, WebFramework.instance_number)
            WebFramework.instance_number = WebFramework.instance_number + 1

        extra_metadata.update({ "bridge.uid": self.uid })

        self._handler_broadcast = plugins.register_handler(self._broadcast, type="sending", extra_metadata=extra_metadata)
        self._handler_repeat = plugins.register_handler(self._repeat, type="allmessages", extra_metadata=extra_metadata)

        self.start_listening(bot)

    def close(self):
        plugins.deregister_handler(self._handler_broadcast, type="sending")
        plugins.deregister_handler(self._handler_repeat, type="allmessages")

    def load_configuration(self, configkey):
        self.configuration = self.bot.get_config_option(self.configkey) or []
        return self.configuration

    def setup_plugin(self):
        logger.warning("setup_plugin should be overridden by derived class")

    def applicable_configuration(self, conv_id):
        """standardised configuration structure:

            "<EXTERNAL_CHAT_NAME>": [
                {
                    "bot_api_key": <api key(s) for bot>,
                    "hangouts": [
                        "<at least 1 internal chat/group/team id>"
                    ],
                    "<EXTERNAL_CHAT_NAME>": [
                        "<at least 1 external chat/group/team id>"
                    ]
                }
            ]

        """

        self.load_configuration(self.configkey)

        applicable_configurations = []
        for configuration in self.configuration:
            if conv_id in configuration["hangouts"]:
                applicable_configurations.append({ "trigger": conv_id,
                                                   "config.json": configuration })

        return applicable_configurations

    @asyncio.coroutine
    def _broadcast(self, bot, broadcast_list, context):
        conv_id = broadcast_list[0][0]
        message = broadcast_list[0][1]
        image_id = broadcast_list[0][2]

        applicable_configurations = self.applicable_configuration(conv_id)
        if not applicable_configurations:
            return

        passthru = context["passthru"]

        if "norelay" not in passthru:
            passthru["norelay"] = []
        if self.uid in passthru["norelay"]:
            # prevent message broadcast duplication
            logger.info("{}:{}:NORELAY:broadcast:{}".format(self.plugin_name, self.uid, passthru["norelay"]))
            return
        else:
            # halt messaging handler from re-relaying
            passthru["norelay"].append(self.uid)

        user = self.bot._user_list._self_user
        chat_id = user.id_.chat_id

        # context preserves as much of the original request as possible

        logger.info("{}:{}:broadcast:{}".format(self.plugin_name, self.uid, passthru["norelay"]))

        if "original_request" in passthru:
            message = passthru["original_request"]["message"]
            image_id = passthru["original_request"]["image_id"]
            if "user" in passthru["original_request"]:
                if(isinstance(passthru["original_request"]["user"], str)):
                    user = FakeUser( full_name = str,
                                     id_ = FakeUserID( chat_id = chat_id,
                                                       gaia_id = chat_id ))
                else:
                    user = passthru["original_request"]["user"]
            else:
                # add bot if no user is present
                passthru["original_request"]["user"] = user

        else:
            """bot is raising an event that needs to be repeated

            only the first handler to run will assign all the variables 
                we need for the other bridges to work"""

            logger.info("hangouts bot raised an event, first seen by {}, {}".format(self.plugin_name, self.uid))

            message = html_to_hangups_markdown(message)

            passthru["original_request"] = { "message": message,
                                             "image_id": image_id,
                                             "segments": None,
                                             "user": user }

            passthru["chatbridge"] = { "source_title": bot.conversations.get_name(conv_id),
                                       "source_user": user,
                                       "source_uid": chat_id,
                                       "source_gid": conv_id,
                                       "source_plugin": self.plugin_name }

        # for messages from other plugins, relay them
        for config in applicable_configurations:
            yield from self._send_to_external_chat(
                config,
                FakeEvent(
                    text = message,
                    user = user,
                    passthru = passthru ))

    @asyncio.coroutine
    def _repeat(self, bot, event, command):
        conv_id = event.conv_id

        applicable_configurations = self.applicable_configuration(conv_id)
        if not applicable_configurations:
            return

        passthru = event.passthru

        if "norelay" not in passthru:
            passthru["norelay"] = []
        if self.uid in passthru["norelay"]:
            # prevent message relay duplication
            logger.info("{}:{}:NORELAY:repeat:{}".format(self.plugin_name, self.uid, passthru["norelay"]))
            return
        else:
            # halt sending handler from re-relaying
            passthru["norelay"].append(self.uid)

        logger.info("{}:{}:repeat:{}".format(self.plugin_name, self.uid, passthru["norelay"]))

        user = event.user
        message = event.text
        image_id = None
        is_action = False

        if "original_request" not in passthru:
            """user has raised an event that needs to be repeated

            only the first handler to run will assign all the variables 
                we need for the other bridges to work"""

            logger.info("hangouts user raised an event, first seen by {}".format(self.plugin_name))

            if (hasattr(event, "conv_event") and isinstance(event.conv_event, ChatMessageEvent) and
                    any(a.type == 4 for a in event.conv_event._event.chat_message.annotation)):
                # This is a /me message sent from desktop Hangouts.
                is_action = True
                # The user's first name prefixes the message, so try to strip that.
                name = self._get_user_details(event.user).get("full_name")
                if name:
                    # We don't have a clear-cut first name, so try to match parts of names.
                    # Try the full name first, then split successive words off the end.
                    parts = name.split()
                    for pos in range(len(parts), 0, -1):
                        sub_name = " ".join(parts[:pos])
                        if message.startswith(sub_name):
                            message = message[len(sub_name) + 1:]
                            break
                    else:
                        # Couldn't match the user's name to the message text.
                        # Possible mismatch between permamem and Hangouts?
                        logger.warn("/me message: couldn't match name '{}' ({}) with message text"
                                    .format(name, user_id))

            attach = None
            if hasattr(event, "conv_event") and getattr(event.conv_event, "attachments"):
                attach = event.conv_event.attachments[0]
                if attach == message:
                    # Message consists solely of the attachment URL, no need to send that.
                    message = "shared an image"
                    is_action = True
                elif attach in message:
                    # Message includes some text too, strip the attachment URL from the end if present.
                    message = message.replace("\n{}".format(attach), "")

            passthru["original_request"] = { "message": message,
                                             "image_id": None, # XXX: should be attachments
                                             "attachments": event.conv_event.attachments,
                                             "segments": event.conv_event.segments,
                                             "user": event.user }

            passthru["chatbridge"] = { "source_title": bot.conversations.get_name(conv_id),
                                       "source_user": event.user,
                                       "source_uid": event.user.id_.chat_id,
                                       "source_gid": conv_id,
                                       "source_action": is_action,
                                       "source_edit": False,
                                       "source_plugin": self.plugin_name }

        for config in applicable_configurations:
            yield from self._send_to_external_chat(config, event)

    @asyncio.coroutine
    def _send_to_external_chat(self, config, event):
        pass

    @asyncio.coroutine
    def _send_to_internal_chat(self, conv_id, message, external_context, image_id=None):
        formatted_message = self.format_incoming_message(message, external_context)

        source_user = self.plugin_name
        if "source_user" in external_context:
            source_user = external_context["source_user"]

        source_title = self.plugin_name
        if "source_title" in external_context:
            source_title = external_context["source_title"]

        source_gid = self.plugin_name
        if "source_gid" in external_context:
            source_gid = external_context["source_gid"]

        source_uid = False
        linked_hangups_user = False
        if "source_uid" in external_context:
            source_uid = external_context["source_uid"]
            linked_hangups_user = self.map_external_uid_with_hangups_user(source_uid, external_context)
            if linked_hangups_user:
                source_user = linked_hangups_user

        passthru =  {
            "original_request": {
                "message": message,
                "image_id": image_id,
                "segments": None,
                "user": source_user },
            "chatbridge": {
                "source_title": source_title,
                "source_user": source_user,
                "source_uid": source_uid,
                "source_gid": source_gid,
                "source_edited": external_context.get("source_edited"),
                "source_action": external_context.get("source_action"),
                "plugin": self.plugin_name },
            "norelay": [ self.uid ] }

        if linked_hangups_user:
            passthru["executable"] = "{}-{}".format(self.plugin_name, str(uuid.uuid4()))

        logger.info("{}:receive:{}".format(self.plugin_name, passthru))

        yield from self.bot.coro_send_message(
            conv_id,
            formatted_message,
            image_id = image_id,
            context = { "passthru": passthru })

    def map_external_uid_with_hangups_user(self, source_uid, external_context):
        return False

    def format_incoming_message(self, message, external_context):
        source_user = external_context.get("source_user") or self.plugin_name
        bridge_user = self._get_user_details(source_user, external_context)
        source_title = external_context.get("source_title")
        source_attrs = [source_title] if source_title else []
        if external_context.get("source_edited"):
            source_attrs.append("edited")

        sender = "<b>{}</b>".format(bridge_user["preferred_name"])
        if source_attrs:
            sender = "{} ({})".format(sender, ", ".join(source_attrs))

        template = "<i>{} {}</i>" if external_context.get("source_action") else "{}: {}"
        return template.format(sender, message)

    def format_outgoing_message(self, message, internal_context):
        formatted = message

        return formatted

    def _get_user_details(self, user, external_context=None):
        chat_id = None
        preferred_name = None # guaranteed
        full_name = None
        nickname = None
        photo_url = None

        if isinstance(user, str):
            full_name = user
        else:
            chat_id = user.id_.chat_id
            permauser = self.bot.get_hangups_user(chat_id)
            nickname = self.bot.get_memory_suboption(chat_id, 'nickname') or None
            if isinstance(permauser, dict):
                full_name = permauser["full_name"]
                if "photo_url" in permauser:
                    photo_url = permauser["photo_url"]
            else:
                full_name = permauser.full_name
                photo_url = permauser.photo_url
            if photo_url and not photo_url.startswith("http"):
                photo_url = "https:" + photo_url

        if nickname:
            preferred_name = nickname
        else:
            preferred_name = full_name

        if not chat_id:
            chat_id = False

        return { "chat_id": chat_id,
                 "preferred_name": preferred_name,
                 "nickname": nickname,
                 "full_name": full_name,
                 "photo_url": photo_url }

    def _format_message(self, message, user, userwrap="MARKDOWN_BOLD2"):
        if userwrap == "MARKDOWN_BOLD": # telegram/slack
            userwrap_left = "*"
            userwrap_right = "*"
        elif userwrap == "MARKDOWN_BOLD2": # github/hangups/hangoutsbot
            userwrap_left = "**"
            userwrap_right = "**"
        elif userwrap == "HTML_BOLD":
            userwrap_left = "<b>"
            userwrap_right = "</b>"
        else:
            userwrap_left = ""
            userwrap_right = ""

        if isinstance(user, str):
            formatted_message = "{2}{0}{3}: {1}".format(user, message, userwrap_left, userwrap_right)
        else:
            bridge_user = self._get_user_details(user)
            formatted_message = "{2}{0}{3}: {1}".format(bridge_user["preferred_name"], message, userwrap_left, userwrap_right)

        return formatted_message

    def start_listening(self, bot):
        loop = asyncio.get_event_loop()

        itemNo = -1
        threads = []

        if isinstance(self.configuration, list):
            for listener in self.configuration:
                itemNo += 1

                try:
                    certfile = listener["certfile"]
                    if not certfile:
                        logger.warning("config.{}[{}].certfile must be configured".format(self.configkey, itemNo))
                        continue
                    name = listener["name"]
                    port = listener["port"]
                except KeyError as e:
                    logger.warning("config.{}[{}] missing keyword".format(self.configkey, itemNo))
                    continue

                aiohttp_start(
                    bot,
                    name,
                    port,
                    certfile,
                    self.RequestHandler,
                    "webbridge." + self.configkey)

        logger.info("webbridge.sinks: {} thread(s) started for {}".format(itemNo + 1, self.configkey))
