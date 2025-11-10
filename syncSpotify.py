"""syncSpotify.py
------------------
Fetch a Spotify playlist and download only the tracks not yet present in the
local per-playlist history CSV. History lives in `playlists/<playlist_id>.csv`.

Workflow:
1. Resolve playlist ID from URL/URI/raw ID.
2. Fetch all tracks (paginated) via Spotipy client credentials flow.
3. Load previously downloaded (track, artist) pairs from history.
4. If --dry-run: list new tracks and exit.
5. Otherwise: download each new track (via songDownloader), append to history.

Environment variables (loaded from .env if present):
    SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI (optional)

Caching: Uses a dedicated `.cache_spotify` file instead of Spotipy default `.cache`.
"""

import os
import sys
import argparse
from pathlib import Path
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.cache_handler import CacheFileHandler
from songDownloader import download_song
import csv
from dotenv import load_dotenv

TRACKING_DIR = "playlists"


def get_playlist_id(playlist_url):
    """Extract canonical playlist ID from URL/URI/raw ID."""
    # Common URL form: https://open.spotify.com/playlist/<id>?...
    if "playlist/" in playlist_url:
        return playlist_url.split("playlist/")[1].split("?")[0]
    elif ":playlist:" in playlist_url:
        return playlist_url.split(":playlist:")[1]
    return playlist_url


def get_tracks_from_spotify(playlist_id, sp):
    """Return list of (track_name, first_artist_name) for the playlist.

    Handles pagination by following `next` until exhausted.
    """
    results = sp.playlist_tracks(playlist_id)
    tracks = []
    while results:
        for item in results["items"]:
            track = item["track"]
            name = track["name"]
            artist = track["artists"][0]["name"]
            tracks.append((name, artist))
        if results["next"]:
            results = sp.next(results)
        else:
            results = None
    return tracks


def load_downloaded_set(history_path):
    """Load previously downloaded (track, artist) pairs as a normalized set."""
    downloaded = set()
    if os.path.exists(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    downloaded.add((row[0].strip().lower(), row[1].strip().lower()))
    return downloaded


def append_to_history(history_path, track, artist):
    """Append one (track, artist) line to the playlist history CSV."""
    with open(history_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([track, artist])


def main():
    """CLI entrypoint: orchestrates sync logic and prints progress."""
    # ---- Argument parsing ----
    parser = argparse.ArgumentParser(
        description="Sync Spotify playlist and download new songs."
    )
    parser.add_argument("playlist_url", help="Spotify playlist link or URI")
    parser.add_argument("download_folder", help="Folder to download songs into")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List new songs not in history without downloading or recording",
    )
    args = parser.parse_args()

    # ---- Load environment variables ----
    load_dotenv()

    # ---- Configure Spotify client credentials flow ----
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: Spotify credentials not set in environment variables.")
        sys.exit(1)

    # Use a custom cache file instead of default .cache
    cache_path = Path(__file__).parent / ".cache_spotify"
    cache_handler = CacheFileHandler(cache_path=str(cache_path))
    sp = Spotify(auth_manager=SpotifyClientCredentials(cache_handler=cache_handler))

    # ---- Fetch playlist tracks ----
    playlist_id = get_playlist_id(args.playlist_url)
    tracks = get_tracks_from_spotify(playlist_id, sp)

    # Setup tracking
    # ---- Load / prepare history ----
    os.makedirs(TRACKING_DIR, exist_ok=True)
    history_path = os.path.join(TRACKING_DIR, f"{playlist_id}.csv")
    downloaded = load_downloaded_set(history_path)

    print(f"Found {len(tracks)} tracks in playlist.", flush=True)

    # Determine new tracks not yet in history
    new_tracks = []
    for track, artist in tracks:
        # Normalize to lowercase for consistent comparison
        key = (track.strip().lower(), artist.strip().lower())
        if key not in downloaded:
            new_tracks.append((track, artist))

    if args.dry_run:
        print(f"New tracks not in history ({len(new_tracks)}):", flush=True)
        for track, artist in new_tracks:
            print(f"  - {artist} - {track}", flush=True)
        # Do not download or write history in dry run
        return

    # ---- Download loop ----
    new_downloads = 0
    for track, artist in new_tracks:
        print(f"Downloading: {artist} - {track}", flush=True)
        success = download_song(track, artist, args.download_folder)
        if success:
            append_to_history(history_path, track, artist)
            print(f"[OK] Downloaded and recorded: {artist} - {track}", flush=True)
            new_downloads += 1
        else:
            print(f"[FAIL] Failed to download: {artist} - {track}", flush=True)
    print(f"Sync complete. {new_downloads} new tracks downloaded.", flush=True)


if __name__ == "__main__":
    main()
