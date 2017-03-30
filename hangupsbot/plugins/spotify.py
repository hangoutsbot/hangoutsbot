# coding: utf-8
"""
Creates a Spotify playlist per chat and adds music automatically by listening
for YouTube, Soundcloud, and Spotify links (or manually with a Spotify query).
"""

import aiohttp
import asyncio
import io
import json
import logging
import os
import re
import plugins

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError as YouTubeHTTPError
from requests.exceptions import HTTPError as SoundcloudHTTPError
from spotipy.client import SpotifyException

import soundcloud
import spotipy
import spotipy.util


logger = logging.getLogger(__name__)


class SpotifyTrack:
    def __init__(self, track_id, track_name, track_artist):
        self.id = track_id
        self.name = track_name
        self.artist = track_artist


class SpotifyPlaylist:
    def __init__(self, playlist_owner, playlist_id, playlist_url):
        self.owner = playlist_owner
        self.id = playlist_id
        self.url = playlist_url


def _initialise():
    plugins.register_handler(_watch_for_music_link, type="message")
    plugins.register_user_command(["spotify"])


@asyncio.coroutine
def _watch_for_music_link(bot, event, command):
    if event.user.is_self:
        return

    # Start with Spotify off.
    enabled = bot.conversation_memory_get(event.conv_id, "spotify_enabled")
    if enabled == None:
        bot.conversation_memory_set(event.conv_id, "spotify_enabled", False)
        return

    if not enabled or "/bot" in event.text:
        return

    links = extract_music_links(event.text)
    if not links: return

    for link in links:
        logger.info("Music link: {}".format(link))

        if "spotify" in link:
            sp = spotipy.Spotify() # track info doesn't require user auth
            tr = sp.track(link)
            track = SpotifyTrack(tr["id"], tr["name"], tr["artists"][0]["name"])
            success = add_to_playlist(bot, event, track)
        else:
            if "youtube" in link or "youtu.be" in link:
                query = title_from_youtube(bot, link)
            elif "soundcloud" in link:
                query = title_from_soundcloud(bot, link)
            else:
                logger.debug("Why are we here? {}".format(link))
                return

            if query:
                success = add_to_spotify(bot, event, query)
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
    if enabled == None:
        enabled = False
        bot.conversation_memory_set(event.conv_id, "spotify_enabled", enabled)

    if not args:
        s = "on" if enabled else "off"
        result = _("<em>Spotify is <b>{}</b>.</em>".format(s))
    else:
        command = args[0]

        if command == "on" or command == "off":
            s = "was" if enabled else "wasn't"
            enabled = command == "on"
            result = _("<em>Spotify {} on. Now it's <b>{}</b>.</em>"
                       .format(s, command))
            bot.conversation_memory_set(
                event.conv_id, "spotify_enabled", enabled)
        elif not enabled:
            result = _(("<em>Spotify is <b>off</b>. To turn it on, "
                        "use <b>/bot spotify on</b></em>"))
        elif command == "help" and len(args) == 1:
            result = _("<em>Did you mean <b>/bot help spotify</b>?</em>")
        elif command == "playlist" and len(args) == 1:
            playlist = chat_playlist(bot, event)
            result = _("<em>Spotify playlist: {}</em>".format(playlist.url))
        elif command == "remove" and len(args) < 3:
            if len(args) == 1 or not "spotify.com/track/" in args[1]:
                result = _("<em>You must specify a Spotify track.</em>")
            else:
                result = remove_from_playlist(bot, event, args[1])
        else:
            query = " ".join(args)
            result = add_to_spotify(bot, event, query)

    yield from bot.coro_send_message(event.conv_id, result)


def extract_music_links(text):
    """Returns an array of music URLs. Currently searches only for YouTube,
    Soundcloud, and Spotify links."""
    m = re.compile(("(https?://)?([a-z0-9.]*?\.)?(youtube.com/|youtu.be/|"
                    "soundcloud.com/|spotify.com/track/)"
                    "([\w.,@?^=%&:/~+#-]*[\w@?^=%&/~+#-])"))
    links = m.findall(text)
    links = ["".join(link) for link in links]

    # Turn all URIs into URLs (necessary for the Spotify API).
    return [l if re.match("https?://", l) else "https://" + l for l in links]


def add_to_spotify(bot, event, query):
    """Searches Spotify for the query and adds the first search result
    to the playlist. Returns a status string."""
    track = search_spotify(query)
    if track:
        return add_to_playlist(bot, event, track)
    else:
        result = _("<em>No tracks found for '{}'.</em>".format(query))
        logger.info(result)
        return result


def search_spotify(query):
    """Searches spotify for the cleaned query and returns the first search
    result, if one exists."""
    bl_following = ["official", "with", "prod", "by", "from"]
    bl_remove = ["freestyle", "acoustic", "original", "&"]
    bl_contains = ["live", "session", "sessions", "edit", "premiere", "cover",
                   "lyric", "lyrics", "records", "release", "video", "audio",
                   "in the open"]

    gs = _clean(query)
    result = _search(gs)
    if result: return result

    # Discard hashtags and mentions.
    gs[:] = [" ".join(re.sub("(@[A-Za-z0-9]+)|(#[A-Za-z0-9]+)",
                             " ", g).split()) for g in gs]

    # Discard everything in a group following certain words.
    for b in bl_following:
        gs[:] = [re.split(b, g, flags=re.IGNORECASE)[0] for g in gs]
    result = _search(gs)
    if result: return result

    # Discard certain words.
    for b in bl_remove:
        match = re.compile(re.escape(b), re.IGNORECASE)
        gs[:] = [match.sub("", g) for g in gs]
    result = _search(gs)
    if result: return result

    # Aggressively discard groups.
    gs[:] = [g for g in gs if not any(b in g.lower() for b in bl_contains)]
    return _search(gs)


def _clean(query):
    """Splits the query into groups and attempts to remove extraneous groups
    unrelated to the song title/artist. Returns a list of groups."""

    # Blacklists.
    bl_exact = ["official", "audio", "audio\s+stream", "lyric", "lyrics",
                "with\s+lyrics?", "explicit", "clean", "explicit\s+version",
                "clean\s+version", "original\s+version", "hq", "hd", "mv", "m/v",
                "interscope", "4ad"]
    bl_following = ["official\s+video", "official\s+music", "official\s+audio",
                    "official\s+lyric", "official\s+lyrics", "official\s+clip",
                    "video\s+lyric", "video\s+lyrics", "video\s+clip",
                    "full\s+video"]

    # Split into groups.
    gs = list(filter(
        None,
        re.split(u"\s*[-‐‒–—―−~\(\)\[\]\{\}\<\>\|‖¦:;‘’“”\"«»„‚‘]+\s*",
                 query)))

    # Discard groups that match with anything in the blacklists.
    gs[:] = [g for g in gs if g.lower() not in bl_exact]
    for b in bl_following:
        gs[:] = [re.split(b, g, flags=re.IGNORECASE)[0] for g in gs]

    # Discard featured artists.
    gs[:] = [re.split("(f(ea)?t(.|\s+))(?i)", g)[0] for g in gs]

    return gs


def _search(groups):
    try:
        sp = spotipy.Spotify() # search doesn't require user auth
        query = " ".join(filter(None, groups))
        logger.info("Searching Spotify for '{}'".format(query))
        results = sp.search(query)
    except SpotifyException as e:
        logger.error("<b>Error when searching Spotify:</b> {}".format(e))
        return ""

    if results["tracks"]["total"]:
        tr = results["tracks"]["items"][0]
        return SpotifyTrack(tr["id"], tr["name"], tr["artists"][0]["name"])
    else:
        return None


def add_to_playlist(bot, event, track):
    playlist = chat_playlist(bot, event)

    try:
        spotify_client(bot).user_playlist_remove_all_occurrences_of_tracks(
            playlist.owner, playlist.id, [track.id])
        spotify_client(bot).user_playlist_add_tracks(
            playlist.owner, playlist.id, [track.id])
        return _("<em>Added <b>{} by {}</b></em>"
                 .format(track.name, track.artist))
    except SpotifyException as e:
        return _("<em><b>Unable to add track:</b> {}</em>".format(e))


def remove_from_playlist(bot, event, track):
    playlist = chat_playlist(bot, event)

    try:
        sp = spotify_client(bot)
        sp.user_playlist_remove_all_occurrences_of_tracks(
            playlist.owner, playlist.id, [track])
        tr = sp.track(track)
        return _("<em>Removed track <b>{} by {}</b>.</em>"
                 .format(tr["name"], tr["artists"][0]["name"]))
    except SpotifyException as e:
        return _("<em><b>Unable to remove track:</b> {}</em>".format(e))


def chat_playlist(bot, event):
    """Creates a playlist for the chat if it doesn't exist."""
    try:
        spotify_user = bot.config.get_by_path(["spotify", "spotify", "user"])
    except (KeyError, TypeError) as e:
        logger.error("<b>Spotify user isn't configured:</b> {}".format(e))
        spotify_user = None

    playlist_id = bot.conversation_memory_get(event.conv_id,
                                              "spotify_playlist_id")
    playlist_url = bot.conversation_memory_get(event.conv_id,
                                               "spotify_playlist_url")
    if not playlist_id:
        playlist_name = bot.conversations.get_name(event.conv_id)
        if not playlist_name: playlist_name = event.conv_id

        playlist = spotify_client(bot).user_playlist_create(
            spotify_user, playlist_name)
        playlist_id = playlist["id"]
        playlist_url = playlist["external_urls"]["spotify"]
        logger.info("New Spotify playlist created: ({}, {})"
                    .format(playlist_id, playlist_url))

        bot.conversation_memory_set(
            event.conv_id, "spotify_playlist_id", playlist_id)
        bot.conversation_memory_set(
            event.conv_id, "spotify_playlist_url", playlist_url)

    return SpotifyPlaylist(spotify_user, playlist_id, playlist_url)


def title_from_youtube(bot, url):
    try:
        youtube_api_key = bot.config.get_by_path(["spotify", "youtube"])
        youtube_client = build("youtube", "v3", developerKey=youtube_api_key)
    except (KeyError, TypeError) as e:
        logger.error("<b>YouTube API key isn't configured:</b> {}".format(e))
        return ""

    # Regex by mantish from http://stackoverflow.com/a/9102270 to get the
    # video id from a YouTube URL.
    match = re.match(
        "^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*", url)
    if match and len(match.group(2)) == 11:
        video_id = match.group(2)
    else:
        logger.error("Unable to extract video id: {}".format(url))
        return ""

    # YouTube response is JSON.
    try:
        response = youtube_client.videos().list(part="snippet",
                                                id=video_id).execute()
        items = response.get("items", [])
        if items:
            return items[0]["snippet"]["title"]
        else:
            logger.error("<b>YouTube response was empty:</b> {}"
                         .format(response))
            return ""
    except YouTubeHTTPError as e:
        logger.error("Unable to get video entry from {}, {}".format(url, e))
        return ""


def title_from_soundcloud(bot, url):
    try:
        soundcloud_id = bot.config.get_by_path(["spotify", "soundcloud"])
        soundcloud_client = soundcloud.Client(client_id=soundcloud_id)
    except (KeyError, TypeError) as e:
        logger.error("<b>Soundcloud client ID isn't configured:</b> {}"
                     .format(e))
        return ""

    try:
        track = soundcloud_client.get("/resolve", url=url)
        return track.title
    except SoundcloudHTTPError as e:
        logger.error("Unable to resolve url {}, {}".format(url, e))
        return ""


def spotify_client(bot):
    """Spotify access requires user authorization. The refresh token is stored
    in memory to circumvent logging in after the initial authorization."""
    try:
        spotify_client_id = bot.config.get_by_path(
            ["spotify", "spotify", "client_id"])
        spotify_client_secret = bot.config.get_by_path(
            ["spotify", "spotify", "client_secret"])
        spotify_redirect_uri = bot.config.get_by_path(
            ["spotify", "spotify", "redirect_uri"])
        spotify_user = bot.config.get_by_path(["spotify", "spotify", "user"])
    except (KeyError, TypeError) as e:
        logger.error("<b>Spotify authorization isn't configured:</b> {}"
                     .format(e))
        return None

    if bot.memory.exists(["spotify", "token"]):
        old_spotify_token = bot.memory.get_by_path(["spotify", "token"])
    else:
        old_spotify_token = ""

    spotify_token = spotipy.util.prompt_for_user_token(
        spotify_user,
        scope="playlist-modify-public playlist-modify-private",
        client_id=spotify_client_id,
        client_secret=spotify_client_secret,
        redirect_uri=spotify_redirect_uri)

    if old_spotify_token and old_spotify_token != spotify_token:
        bot.memory.set_by_path(["spotify", "token"], spotify_token)

    return spotipy.Spotify(auth=spotify_token)
