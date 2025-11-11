import os
import re
import argparse
from dotenv import load_dotenv
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from yt_dlp import YoutubeDL
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, error, TIT2, TPE1, TALB, TCON
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    print("Warning: .env file not found. Make sure to set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET environment variables.")

# --- CONFIGURATION ---
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
DOWNLOAD_DIR = r"./newThingDownloads"

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    print("Error: SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set in .env file or environment variables.")
    exit(1)


# --- AUTHENTICATE SPOTIFY ---
sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
)

def get_playlist_tracks(playlist_url):
    """Fetch all track info from a Spotify playlist"""
    results = sp.playlist_tracks(playlist_url)
    tracks = results['items']

    while results['next']:
        results = sp.next(results)
        tracks.extend(results['items'])

    songs = []
    for item in tracks:
        track = item['track']
        if track is None:
            continue

        artist = track['artists'][0]['name']
        track_name = track['name']
        album = track['album']['name']
        cover_url = track['album']['images'][0]['url'] if track['album']['images'] else None
        track_id = track['artists'][0]['id']

        # Fetch genre (from artist metadata)
        genre = None
        try:
            artist_info = sp.artist(track_id)
            if artist_info['genres']:
                genre = artist_info['genres'][0].title()
        except Exception:
            genre = None

        songs.append({
            "artist": artist,
            "title": track_name,
            "album": album,
            "cover_url": cover_url,
            "genre": genre
        })
    return songs


class YTDlpLogger:
    """Silence yt-dlp logs by implementing a no-op logger."""
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def download_from_youtube(song):
    """Download song from YouTube and convert to MP3"""
    query = f"{song['artist']} {song['title']}"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_DIR, f"{song['title']}.%(ext)s"),
        'quiet': True,
        'no_warnings': True,
        'logger': YTDlpLogger(),
        'postprocessors': [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}
        ],
        # Reduce ffmpeg chatter to errors only
        'postprocessor_args': ['-loglevel', 'error'],
    }

    with YoutubeDL(ydl_opts) as ydl:
        print(f"🎧 Downloading: {query}")
        ydl.download([f"ytsearch1:{query}"])

    return os.path.join(DOWNLOAD_DIR, f"{song['title']}.mp3")


def apply_metadata(mp3_path, song):
    """Apply Spotify metadata and cover art"""
    try:
        audio = MP3(mp3_path, ID3=ID3)
        try:
            audio.add_tags()
        except error:
            pass

        # Apply text metadata
                # Apply text metadata
        audio["TIT2"] = TIT2(encoding=3, text=song['title'])
        audio["TPE1"] = TPE1(encoding=3, text=song['artist'])
        audio["TALB"] = TALB(encoding=3, text=song['album'])
        if song['genre']:
            audio["TCON"] = TCON(encoding=3, text=song['genre'])

        # Apply album art
        if song['cover_url']:
            img_data = requests.get(song['cover_url']).content
            audio.tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc=u"Cover",
                    data=img_data,
                )
            )
        audio.save()
        print(f"✅ Tagged: {song['artist']} - {song['title']}\n")
    except Exception as e:
        print(f"⚠️ Metadata error for {song['title']}: {e}")


def process_song(song):
    """Download and apply metadata to a single song (for threading)"""
    try:
        mp3_path = download_from_youtube(song)
        apply_metadata(mp3_path, song)
        return True, song['title']
    except Exception as e:
        print(f"⚠️ Error processing {song['title']}: {e}")
        return False, song['title']


def main():
    parser = argparse.ArgumentParser(
        description="Download tracks from a Spotify playlist with metadata and album art."
    )
    parser.add_argument(
        "--playlist",
        required=True,
        help="Spotify playlist URL, URI, or ID"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Download directory (default: from DOWNLOAD_DIR env var or 'downloads')"
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Number of concurrent downloads (default: 4)"
    )
    args = parser.parse_args()

    # Temporarily override DOWNLOAD_DIR for this run if specified
    global DOWNLOAD_DIR
    if args.output_dir:
        DOWNLOAD_DIR = args.output_dir
    
    # Create the download directory
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    songs = get_playlist_tracks(args.playlist)
    print(f"\nFound {len(songs)} tracks in playlist.\n")
    print(f"Downloading with {args.threads} concurrent threads...\n")

    successful = 0
    failed = 0

    # Use ThreadPoolExecutor for concurrent downloads
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        # Submit all download jobs
        futures = {executor.submit(process_song, song): song for song in songs}
        
        # Process completed downloads as they finish
        for future in as_completed(futures):
            success, title = future.result()
            if success:
                successful += 1
            else:
                failed += 1

    print(f"\n{'='*50}")
    print(f"Download Complete!")
    print(f"Successful: {successful}/{len(songs)}")
    print(f"Failed: {failed}/{len(songs)}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
