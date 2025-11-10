#!/usr/bin/env python3
"""
checkPlaylist_Spotify.py

Query a Spotify playlist and behave like the Apple Music checker:
- Find new tracks compared to a history CSV (default: `EDM_Justin.csv`)
- Write a CSV compatible with `csvDownloader.py` containing only new tracks
- For each new track, call `csvDownloader.py` with a single-track CSV and only add to history on success

Dependencies:
- spotipy (pip install spotipy)
- A Spotify App with client id/secret and a redirect URI configured
  Required env vars for user auth flow: SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI
  Scope used: playlist-read-private (for private playlists). Public playlists only may work with client credentials, but user auth is more general.

Usage examples:
  python checkPlaylist_Spotify.py --playlist "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M" --output-dir downloads
  python checkPlaylist_Spotify.py --playlist "37i9dQZF1DXcBWIGoYBM5M" --dry-run

Note: This script does not install dependencies or run the downloader automatically; it expects `csvDownloader.py` to be present in the same directory.
"""

import argparse
import csv
import datetime
import os
import sys
import tempfile
import subprocess
from typing import List, Tuple

# Attempt to import required packages
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing dependency: {str(e)}")
    print("Install required packages with: pip install spotipy python-dotenv")
    sys.exit(1)

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    print("Warning: .env file not found. Make sure to set SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and SPOTIPY_REDIRECT_URI environment variables.")


TRACK_NAME_COLUMN = "Track Name"
ARTIST_NAME_COLUMN = "Artist Name(s)"

def read_processed_set(csv_path: str) -> set:
    processed = set()
    if not os.path.exists(csv_path):
        return processed

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if TRACK_NAME_COLUMN not in reader.fieldnames or ARTIST_NAME_COLUMN not in reader.fieldnames:
                return processed
            for row in reader:
                track = (row.get(TRACK_NAME_COLUMN) or "").strip().lower()
                artist_field = (row.get(ARTIST_NAME_COLUMN) or "").strip()
                first_artist = artist_field.split(";")[0].strip().lower() if artist_field else ""
                if track and first_artist:
                    processed.add((track, first_artist))
    except Exception:
        return set()
    return processed


def extract_playlist_id(playlist_id_or_uri: str) -> str:
    """Extract the playlist ID from a Spotify playlist URL, URI, or ID."""
    # Handle URLs like https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=...
    if "open.spotify.com" in playlist_id_or_uri:
        parts = playlist_id_or_uri.split("/")
        playlist_part = [p for p in parts if p.strip()][-1]  # Get last non-empty part
        return playlist_part.split("?")[0]  # Remove query parameters
    # Handle URIs like spotify:playlist:37i9dQZF1DXcBWIGoYBM5M
    elif "spotify:playlist:" in playlist_id_or_uri:
        return playlist_id_or_uri.split(":")[-1]
    # Already a playlist ID
    else:
        return playlist_id_or_uri.strip()

def parse_spotify_playlist(playlist_id_or_uri: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Return playlist name and list of (track_name, artists_string) from the playlist.

    This uses the user-auth flow (SpotifyOAuth). Ensure environment vars are set.
    Returns: (playlist_name, list_of_tracks)
    """
    if spotipy is None:
        raise RuntimeError("Missing dependency: spotipy. Install it with `pip install spotipy`.")

    # Scope for reading user's playlists (and private playlists if needed)
    scope = "playlist-read-private"
    
    # Use 127.0.0.1 instead of localhost per Spotify's recommendation
    redirect_uri = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    # Use a named cache file so it is obvious and doesn't clash with other tools.
    # You can override via SPOTIPY_CACHE_PATH env var; default will be .cache_spotify
    default_cache = os.path.join(os.path.dirname(__file__), ".cache_spotify")
    cache_path = os.environ.get("SPOTIPY_CACHE_PATH", default_cache)

    auth_manager = SpotifyOAuth(scope=scope, redirect_uri=redirect_uri, cache_path=cache_path)
    sp = spotipy.Spotify(auth_manager=auth_manager)

    # Get playlist details first
    playlist_id = extract_playlist_id(playlist_id_or_uri)
    playlist = sp.playlist(playlist_id, fields="name")
    playlist_name = playlist["name"]

    # Then get all tracks
    items = []
    limit = 100
    offset = 0

    while True:
        resp = sp.playlist_items(playlist_id, offset=offset, limit=limit, fields="items.track.name,items.track.artists,next,total")
        if not resp or 'items' not in resp:
            break
        for it in resp['items']:
            track = it.get('track')
            if not track:
                continue
            name = track.get('name') or ""
            artists = track.get('artists') or []
            artist_names = "; ".join([a.get('name', '').strip() for a in artists if a and a.get('name')])
            if name:
                items.append((name.strip(), artist_names.strip()))
        # pagination
        if not resp.get('next'):
            break
        offset += limit

    return playlist_name, items


def write_new_csv(new_tracks: List[Tuple[str, str]], out_path: str, *, append: bool = False) -> None:
    """Write tracks to CSV. If append=True, append to existing file; otherwise create new."""
    fieldnames = [TRACK_NAME_COLUMN, ARTIST_NAME_COLUMN]
    
    # Create new file with header if not appending or file doesn't exist
    if not append or not os.path.exists(out_path):
        mode = "w"
        write_header = True
    else:
        mode = "a"
        write_header = False
    
    with open(out_path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for track, artist in new_tracks:
            writer.writerow({TRACK_NAME_COLUMN: track, ARTIST_NAME_COLUMN: artist})


def download_single_track(track: str, artist: str, output_dir: str) -> bool:
    fd, tmp_csv = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        write_new_csv([(track, artist)], tmp_csv)
        csvdownloader_path = os.path.join(os.path.dirname(__file__), "csvDownloader.py")
        if not os.path.exists(csvdownloader_path):
            print(f"Error: csvDownloader.py not found at {csvdownloader_path}")
            return False

        cmd = [sys.executable, csvdownloader_path, tmp_csv, output_dir]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # csvDownloader prints a success message per-track; check stdout for that token
        # This is tolerant to small output differences but looks for the human-readable success prefix.
        success = "✅ Success: Downloaded" in (result.stdout or "")

        if not success:
            # Print helpful debug info
            print(f"Failed to download: {artist} - {track}")
            if result.stderr:
                print(f"Error output: {result.stderr}")
            if result.stdout:
                print(f"Download output: {result.stdout}")
        return success
    finally:
        try:
            os.unlink(tmp_csv)
        except OSError:
            pass


def append_to_history(new_tracks: List[Tuple[str, str]], history_path: str) -> None:
    """Add successfully downloaded tracks to the playlist's history file."""
    write_new_csv(new_tracks, history_path, append=True)


def main():
    parser = argparse.ArgumentParser(description="Detect new songs in a Spotify playlist and run csvDownloader on them.")
    parser.add_argument("--playlist", required=True, help="Spotify playlist id, URI or URL to check")
    parser.add_argument("--out-csv", default=None, help="Path to write the new-songs CSV (default: timestamped file in ./csv)")
    parser.add_argument("--output-dir", default="downloads", help="Directory where downloads will be stored")
    parser.add_argument("--dry-run", action="store_true", help="Only print which songs would be added / downloaded, don't run downloader")
    parser.add_argument("--history", default=None, help="Path to history CSV (default: EDM_Justin.csv next to this script)")
    args = parser.parse_args()

    if spotipy is None:
        print("Missing dependency: spotipy. Install it with `pip install spotipy` and ensure SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI are set for user auth if needed.")
        sys.exit(1)

    # Set up playlists directory
    playlists_dir = os.path.join(os.path.dirname(__file__), "playlists")
    os.makedirs(playlists_dir, exist_ok=True)

    try:
        # Get playlist ID and tracks
        playlist_id = extract_playlist_id(args.playlist)
        playlist_name, playlist_tracks = parse_spotify_playlist(args.playlist)
        
        # Use playlist ID for the history file name
        history_path = args.history or os.path.join(playlists_dir, f"{playlist_id}.csv")
        processed = read_processed_set(history_path)
        
        print(f"\nPlaylist: {playlist_name}")
        print(f"ID: {playlist_id}")
        print(f"History file: {history_path}")
        
        if not os.path.exists(history_path):
            print(f"Note: This is a new playlist, no history file exists yet.")
    except Exception as e:
        print(f"Error querying Spotify playlist: {e}")
        sys.exit(1)

    new_tracks = []
    for track_name, artist in playlist_tracks:
        # Normalize track name and artist to match CSV format
        track_clean = track_name.strip()
        # Take all artists but normalize separators to match CSV format
        artist_clean = artist.replace(";", ",").strip()
        
        # For comparison, use lowercase and first artist only
        key = (track_clean.lower(), artist_clean.split(',')[0].strip().lower())
        if key not in processed:
            new_tracks.append((track_clean, artist_clean))

    if not new_tracks:
        print("No new tracks found in playlist. Nothing to do.")
        sys.exit(0)

    print(f"Found {len(new_tracks)} new track(s) in playlist:")
    for t, a in new_tracks:
        print(f"  - {a} - {t}")

        if args.out_csv:
            # Only write to a separate CSV if explicitly requested
            write_new_csv(new_tracks, args.out_csv)
            print(f"Wrote new songs CSV to: {args.out_csv}")

    if args.dry_run:
        print("Dry run requested; not running csvDownloader.")
        sys.exit(0)

    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir, exist_ok=True)

    successful_tracks = []
    failed_tracks = []

    for track, artist in new_tracks:
        print(f"\nProcessing: {artist} - {track}")
        if download_single_track(track, artist, args.output_dir):
            successful_tracks.append((track, artist))
            append_to_history([(track, artist)], history_path)
            print(f"✓ Successfully downloaded and added to history: {artist} - {track}")
        else:
            failed_tracks.append((track, artist))

    print("\n=== Download Summary ===")
    print(f"Total tracks processed: {len(new_tracks)}")
    print(f"Successfully downloaded: {len(successful_tracks)}")
    print(f"Failed to download: {len(failed_tracks)}")
    if failed_tracks:
        print("\nFailed tracks (will be retried next time):")
        for track, artist in failed_tracks:
            print(f"  - {artist} - {track}")

    sys.exit(1 if failed_tracks else 0)


if __name__ == "__main__":
    main()
