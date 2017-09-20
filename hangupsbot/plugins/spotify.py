# coding: utf-8
"""
Creates a Spotify playlist per chat and adds music automatically by listening
for YouTube, Soundcloud, and Spotify links (or manually with a Spotify query).

See https://github.com/hangoutsbot/hangoutsbot/wiki/Spotify-Plugin for help
"""

from collections import namedtuple

import asyncio
import logging
import os
import re

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError as YouTubeHTTPError
from requests.exceptions import HTTPError as SoundcloudHTTPError
from spotipy.client import Spotify, SpotifyException
from spotipy.util import prompt_for_user_token as spotify_get_auth_stdin

import appdirs
import soundcloud

import plugins

logger = logging.getLogger(__name__)


_DETECT_LINKS = re.compile(
    (r"(https?://)?([a-z0-9.]*?\.)?"
     "(youtube.com/|youtu.be/|soundcloud.com/|spotify.com/track/)"
     r"([\w.,@?^=%&:/~+#-]*[\w@?^=%&/~+#-])"))
_YOUTUBE_ID = re.compile(
    r"^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*")
_HAS_PROTOCOLL = re.compile("https?://")

_CLEANUP_CHAR = re.compile(
    r"\s*[-‐‒–—―−~\(\)\[\]\{\}\<\>\|‖¦:;‘’“”\"«»„‚‘]+\s*")
_CLEANUP_HASHTAG_MENTION = re.compile(r"(@[A-Za-z0-9]+)|(#[A-Za-z0-9]+)")
_CLEANUP_FOLLOWING = ("official", "with", "prod", "by", "from")
_CLEANUP_REMOVE = ("freestyle", "acoustic", "original", "&")
_CLEANUP_CONTAINS = ("live", "session", "sessions", "edit", "premiere", "cover",
                     "lyric", "lyrics", "records", "release", "video", "audio",
                     "in the open")
_CLEANUP_FEAT = re.compile(r"(f(ea)?t(.|\s+))(?i)")

_BLACKLIST_EXACT = ("official", "audio", r"audio\s+stream", "lyric", "lyrics",
                    r"with\s+lyrics?", "explicit", "clean", "hq", "hd",
                    r"explicit\s+version", r"clean\s+version", "mv", "m/v",
                    r"original\s+version", "interscope", "4ad")
_BLACKLIST_FOLLOWING = (r"official\s+video", r"official\s+music",
                        r"official\s+audio", r"official\s+lyric",
                        r"official\s+lyrics", r"official\s+clip",
                        r"video\s+lyric", r"video\s+lyrics",
                        r"video\s+clip", r"full\s+video")

class _MissingAuth(Exception):
    """Could not find a token to authenticate an api-call"""

class _PlaylistCreationFailed(Exception):
    """could not create a playlist for a given conversation"""

# pylint:disable=invalid-name
SpotifyTrack = namedtuple("SpotifyTrack", ("id_", "name", "artist"))
SpotifyPlaylist = namedtuple("SpotifyPlaylist", ("owner", "id_", "url"))
# pylint:enable=invalid-name

def _initialise(bot):
    """setup logging and storage, register the user command, listen to messages

    Args:
        bot (hangupsbot.HangupsBot): the running instance
    """
    # suppress a noisy stacktrace and disable logging of every request which
    # also exposes the api-token to the log.
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
    logging.getLogger("googleapiclient.discovery").setLevel(logging.WARNING)

    # the spotify module stores user data in random locations, set a static one
    if not bot.config.exists(["spotify", "spotify"]):
        bot.config.config.setdefault("spotify", {}).setdefault("spotify", {})
    config_path = ["spotify", "spotify", "storage"]
    if not bot.config.exists(config_path):
        bot_id = bot.user_self()["chat_id"]
        real_path = appdirs.user_data_dir(appname="spotify", version=bot_id)
        bot.config.set_by_path(config_path, real_path)
        bot.config.save()

    plugins.register_handler(_watch_for_music_link, "message")
    plugins.register_user_command(["spotify"])

@asyncio.coroutine
def _watch_for_music_link(bot, event):
    """resolve music links to their titles and add the tracks to spotify

    Args:
        bot (hangupsbot.HangupsBot): the running instance
        event (event.ConversationEvent): the currently handled instance
    """
    # Start with Spotify off.
    enabled = bot.conversation_memory_get(event.conv_id, "spotify_enabled")

    # pylint:disable=protected-access
    prefixes = bot._handlers.bot_command
    # pylint:enable=protected-access
    prefixes = tuple(prefixes) if isinstance(prefixes, list) else prefixes
    if not enabled or event.text.startswith(prefixes):
        return

    links = extract_music_links(event.text)
    if not links:
        return

    for link in set(links):
        logger.info("Music link: %s", link)

        if "spotify" in link:
            try:
                spotify_client = get_spotify_client(bot)
            except _MissingAuth:
                break
            raw_track = spotify_client.track(link)
            track = SpotifyTrack(raw_track["id"],
                                 raw_track["name"],
                                 raw_track["artists"][0]["name"])
            success = add_to_playlist(bot, event, track)
        else:
            if "youtube" in link or "youtu.be" in link:
                query = get_title_from_youtube(bot, link)
            elif "soundcloud" in link:
                query = get_title_from_soundcloud(bot, link)

            if query:
                try:
                    success = add_to_spotify(bot, event, query)
                except _MissingAuth:
                    break
            else:
                success = _("<em>Unable to get the song title :(</em>")

        yield from bot.coro_send_message(event.conv.id_, success)

def spotify(bot, event, *args):
    """Commands to manage the Spotify playlist.

    <b>/bot spotify</b> Returns whether Spotify is on or off.

    <b>/bot spotify on/off</b> Turns Spotify on or off.

    <b>/bot spotify playlist</b> Returns the chat's playlist URL.

    <b>/bot spotify <query></b> Directly adds a track to the playlist.

    <b>/bot spotify remove <track></b> Removes the track from the playlist.
    """
    # Start with Spotify off.
    enabled = bot.conversation_memory_get(event.conv_id, "spotify_enabled")

    if not args:
        state = "on" if enabled else "off"
        result = _("<em>Spotify is <b>{}</b>.</em>").format(state)
        yield from bot.coro_send_message(event.conv_id, result)
        return

    command = args[0]

    if command == "on" or command == "off":
        state = "was" if enabled else "wasn't"
        enabled = command == "on"
        result = _("<em>Spotify {} on. Now it's <b>{}</b>.</em>").format(
            state, command)
        bot.conversation_memory_set(
            event.conv_id, "spotify_enabled", enabled)
    elif not enabled:
        result = _("<em>Spotify is <b>off</b>. To turn it on, "
                   "use <b>/bot spotify on</b></em>")
    elif command == "help" and len(args) == 1:
        result = _("<em>Did you mean <b>/bot help spotify</b>?</em>")
    elif command == "playlist" and len(args) == 1:
        try:
            playlist = get_chat_playlist(bot, event)
        except (_MissingAuth, _PlaylistCreationFailed):
            result = _("Failed to create a new playlist for the chat")
        else:
            result = _("<em>Spotify playlist: {}</em>".format(playlist.url))
    elif command == "remove" and len(args) < 3:
        if len(args) == 1 or "spotify.com/track/" not in args[1]:
            result = _("<em>You must specify a Spotify track.</em>")
        else:
            result = remove_from_playlist(bot, event, args[1])
    else:
        query = " ".join(args)
        try:
            result = add_to_spotify(bot, event, query)
        except _MissingAuth:
            result = _("Authentication is missing to file spotify requests")

    yield from bot.coro_send_message(event.conv_id, result)

def extract_music_links(text):
    """get media urls from YouTube, Soundcloud or Spotify

    Args:
        text (str): the source event text

    Returns:
        list: a list of strings, the found media urls
    """
    links = _DETECT_LINKS.findall(text)
    links = ["".join(link) for link in links]

    # Turn all URIs into URLs (necessary for the Spotify API).
    return [l if _HAS_PROTOCOLL.match(l) else "https://" + l for l in links]


def add_to_spotify(bot, event, query):
    """Searches Spotify for the query and adds a found track to the playlist.

    Args:
        bot (hangupsbot.HangupsBot): the running instance
        event (event.ConversationEvent): the currently handled instance

    Returns:
        str: a status string

    Raises:
        _MissingAuth: the spotify auth is not configured
    """
    track = search_spotify(bot, query)
    if track:
        return add_to_playlist(bot, event, track)
    result = _("<em>No tracks found for '{}'.</em>".format(query))
    logger.info(result)
    return result

def search_spotify(bot, query):
    """Searches spotify for the cleaned query

    Args:
        bot (hangupsbot.HangupsBot): the running instance
        query (str)

    Returns:
        str: the first search result

    Raises:
        _MissingAuth: the spotify auth is not configured
    """
    groups = _clean(query)
    result = _search(bot, groups)
    if result:
        return result

    # Discard hashtags and mentions.
    groups = [" ".join(_CLEANUP_HASHTAG_MENTION.sub(" ", g).split())
              for g in groups]

    # Discard everything in a group following certain words.
    for item in _CLEANUP_FOLLOWING:
        groups = [re.split(item, g, flags=re.IGNORECASE)[0] for g in groups]
    result = _search(bot, groups)
    if result:
        return result

    # Discard certain words.
    for item in _CLEANUP_REMOVE:
        match = re.compile(re.escape(item), re.IGNORECASE)
        groups = [match.sub("", g) for g in groups]
    result = _search(bot, groups)
    if result:
        return result

    # Aggressively discard groups.
    groups = [g for g in groups
              if not any(item in g.lower() for item in _CLEANUP_CONTAINS)]
    return _search(bot, groups)

def _clean(query):
    """Splits the query into groups and removes unrelated items.

    Args:
        query (str): noisy track title with extras

    Returns:
        list: a list of string, expected items: the track title and artist
    """
    # Split into groups.
    groups = list(filter(None, _CLEANUP_CHAR.split(query)))

    # Discard groups that match with anything in the blacklists.
    groups = [g for g in groups if g.lower() not in _BLACKLIST_EXACT]
    for item in _BLACKLIST_FOLLOWING:
        groups = [re.split(item, g, flags=re.IGNORECASE)[0] for g in groups]

    # Discard featured artists.
    groups = [_CLEANUP_FEAT.split(g)[0] for g in groups]

    return groups

def _search(bot, groups):
    """perform an api-request to get tracks from spotify

    Args:
        bot (hangupsbot.HangupsBot): the running instance
        groups (list): a list of string, expect tracktitle and artist

    Returns:
        list: a list of `SpotifyTrack`s

    Raises:
        _MissingAuth: there is no auth configured in the bot config
    """
    spotify_client = get_spotify_client(bot)
    query = " ".join(filter(None, groups))
    logger.info("Searching Spotify for '%s'", query)
    try:
        results = spotify_client.search(query)
    except SpotifyException as err:
        logger.error("Error when searching Spotify: %s", repr(err))
        return None

    try:
        if not results["tracks"]["total"]:
            return None

        raw_track = results["tracks"]["items"][0]
        return SpotifyTrack(
            raw_track["id"], raw_track["name"], raw_track["artists"][0]["name"])
    except KeyError as err:
        logger.critical("Spotify API-Change: %s", repr(err))
        return None

def add_to_playlist(bot, event, track):
    """add a track to the conversations spotify playlist

    Args:
        bot (hangupsbot.HangupsBot): the running instance
        event (event.ConversationEvent): the currently handled instance
        track (SpotifyTrack): the track to add

    Returns:
        str: a status string

    Raises:
        _MissingAuth: there is no auth configured in the bot config
    """
    try:
        playlist = get_chat_playlist(bot, event)
    except _PlaylistCreationFailed:
        return _("<i>Unable to create a new playlist for the current "
                 "conversation</i>")

    spotify_client = get_spotify_client(bot)
    try:
        spotify_client.user_playlist_remove_all_occurrences_of_tracks(
            playlist.owner, playlist.id_, [track.id_])
        spotify_client.user_playlist_add_tracks(
            playlist.owner, playlist.id_, [track.id_])
    except SpotifyException as err:
        return _("<em><b>Unable to add track:</b> {}</em>").format(err)
    else:
        return _("<em>Added <b>{} by {}</b></em>").format(
            track.name, track.artist)

def remove_from_playlist(bot, event, track_url):
    """remove a track from the conversations spotify playlist

    Args:
        bot (hangupsbot.HangupsBot): the running instance
        event (event.ConversationEvent): the currently handled instance
        track (SpotifyTrack): the track to remove

    Returns:
        str: a status string

    Raises:
        _MissingAuth: there is no auth configured in the bot config
    """
    try:
        playlist = get_chat_playlist(bot, event)
    except _PlaylistCreationFailed:
        return _("<i>Unable to create a new playlist for the current "
                 "conversation</i>")

    try:
        spotify_client = get_spotify_client(bot)
        spotify_client.user_playlist_remove_all_occurrences_of_tracks(
            playlist.owner, playlist.id_, [track_url])
        raw_track = spotify_client.track(track_url)
    except SpotifyException as err:
        return _("<em><b>Unable to remove track:</b> {}</em>").format(err)

    try:
        return _("<em>Removed track <b>{} by {}</b>.</em>").format(
            raw_track["name"], raw_track["artists"][0]["name"])
    except KeyError as err:
        logger.critical("Spotify API-Change: %s", repr(err))
        return _("<i>Removed track {}, but could not fetch additional "
                 "information about the track</i>").format(track_url)

def get_chat_playlist(bot, event):
    """get a cached playlist for the conversation or create a new one

    Args:
        bot (hangupsbot.HangupsBot): the running instance
        event (event.ConversationEvent): the currently handled instance

    Returns:
        SpotifyPlaylist: the conversations playlist

    Raises:
        _MissingAuth: there is no auth configured in the bot config
        _PlaylistCreationFailed: failed to create a playlist
    """
    try:
        spotify_user = bot.config.get_by_path(["spotify", "spotify", "user"])
    except (KeyError, TypeError) as err:
        logger.error("Spotify user isn't configured: %s", err)
        spotify_user = None

    playlist_id = bot.conversation_memory_get(event.conv_id,
                                              "spotify_playlist_id")
    playlist_url = bot.conversation_memory_get(event.conv_id,
                                               "spotify_playlist_url")
    if not playlist_id:
        playlist_name = bot.conversations.get_name(event.conv_id)
        if not playlist_name:
            playlist_name = event.conv_id

        spotify_client = get_spotify_client(bot)
        try:
            playlist = spotify_client.user_playlist_create(
                spotify_user, playlist_name)
        except SpotifyException:
            logger.exception("core error while creating the playlist %s",
                             playlist_name)
            raise _PlaylistCreationFailed() from None

        try:
            playlist_id = playlist["id"]
            playlist_url = playlist["external_urls"]["spotify"]
        except KeyError as err:
            logger.critical("Spotify API-Change: %s", repr(err))
            raise _PlaylistCreationFailed() from None

        logger.info("New Spotify playlist created: (%s, %s)",
                    playlist_id, playlist_url)

        bot.conversation_memory_set(
            event.conv_id, "spotify_playlist_id", playlist_id)
        bot.conversation_memory_set(
            event.conv_id, "spotify_playlist_url", playlist_url)

    return SpotifyPlaylist(spotify_user, playlist_id, playlist_url)

def get_title_from_youtube(bot, url):
    """get the title of a youtube video

    Args:
        bot (hangupsbot.HangupsBot): the running instance
        url (str): the video URI

    Returns:
        str: the videos title
    """
    try:
        youtube_api_key = bot.config.get_by_path(["spotify", "youtube"])
        youtube_client = build("youtube", "v3", developerKey=youtube_api_key)
    except (KeyError, TypeError) as err:
        logger.error("YouTube API key isn't configured: %s", err)
        return None

    # Regex by mantish from http://stackoverflow.com/a/9102270 to get the
    # video id from a YouTube URL.
    match = _YOUTUBE_ID.match(url)
    if match and len(match.group(2)) == 11:
        video_id = match.group(2)
    else:
        logger.error("Unable to extract video id: %s", url)
        return None

    # YouTube response is JSON.
    try:
        response = youtube_client.videos().list(      # pylint:disable=no-member
            part="snippet", id=video_id).execute()
        items = response.get("items", [])
        if items:
            return items[0]["snippet"]["title"]
        logger.error("YouTube response was empty: %s", response)
        return None
    except (YouTubeHTTPError, KeyError) as err:
        logger.error("Unable to get video entry from %s, %s", url, repr(err))
        return None

def get_title_from_soundcloud(bot, url):
    """get the title of a soundcloud track

    Args:
        bot (hangupsbot.HangupsBot): the running instance
        url (str): the tracks URI

    Returns:
        str: the tracks title
    """
    try:
        soundcloud_id = bot.config.get_by_path(["spotify", "soundcloud"])
        soundcloud_client = soundcloud.Client(client_id=soundcloud_id)
    except (KeyError, TypeError) as err:
        logger.error("Soundcloud client ID isn't configured: %s", err)
        return None

    try:
        track = soundcloud_client.get("/resolve", url=url)
        return track.title
    except SoundcloudHTTPError as err:
        logger.error("Unable to resolve url %s, %s", url, repr(err))
        return None

def get_spotify_client(bot):
    """get a spotify client with configured auth or start the auth process

    Spotify access requires user authorization. The refresh token is stored
    in memory to circumvent logging in after the initial authorization.

    Auth is captured via stdin

    Args:
        bot (hangupsbot.HangupsBot): the running instance

    Returns:
        Spotify: `spotify.client.Spotify`, the spotify client

    Raises:
        _MissingAuth: there is no auth configured in the bot config
    """
    try:
        spotify_client_id = bot.config.get_by_path(
            ["spotify", "spotify", "client_id"])
        spotify_client_secret = bot.config.get_by_path(
            ["spotify", "spotify", "client_secret"])
        spotify_redirect_uri = bot.config.get_by_path(
            ["spotify", "spotify", "redirect_uri"])
        spotify_user = bot.config.get_by_path(["spotify", "spotify", "user"])
        storage_path = bot.config.get_by_path(["spotify", "spotify", "storage"])
    except (KeyError, TypeError) as err:
        logger.error("Spotify authorization isn't configured: %s", err)
        raise _MissingAuth() from None

    if bot.memory.exists(["spotify", "token"]):
        old_spotify_token = bot.memory.get_by_path(["spotify", "token"])
    else:
        old_spotify_token = ""

    if not os.path.exists(storage_path):
        os.makedirs(storage_path)

    old_cwd = os.getcwd()
    os.chdir(storage_path)
    spotify_token = spotify_get_auth_stdin(
        spotify_user,
        scope="playlist-modify-public playlist-modify-private",
        client_id=spotify_client_id,
        client_secret=spotify_client_secret,
        redirect_uri=spotify_redirect_uri)
    os.chdir(old_cwd)

    if old_spotify_token and old_spotify_token != spotify_token:
        bot.memory.set_by_path(["spotify", "token"], spotify_token)

    return Spotify(auth=spotify_token)
