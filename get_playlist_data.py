#!/usr/bin/env python3
"""
Quick script to fetch playlist data from Spotify API and save the raw response.
"""

import os
import json
import argparse
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    print("Error: SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set")
    exit(1)

# Initialize Spotify client
sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
)


def get_playlist_data(playlist_url):
    """Fetch complete playlist data from Spotify API"""
    print(f"Fetching playlist: {playlist_url}\n")
    
    # Get playlist info
    playlist = sp.playlist(playlist_url)
    
    # Get all tracks
    results = sp.playlist_tracks(playlist_url)
    tracks = results['items']
    
    while results['next']:
        results = sp.next(results)
        tracks.extend(results['items'])
    
    # Extract only essential information
    concise_data = {
        'playlist_name': playlist['name'],
        'playlist_id': playlist['id'],
        'owner': playlist['owner']['display_name'],
        'total_tracks': len(tracks),
        'tracks': []
    }
    
    for item in tracks:
        track = item['track']
        if track is None:
            continue
            
        concise_data['tracks'].append({
            'title': track['name'],
            'artist': track['artists'][0]['name'],
            'all_artists': [artist['name'] for artist in track['artists']],
            'album': track['album']['name'],
            'duration_ms': track['duration_ms'],
            'track_id': track['id'],
            'track_uri': track['uri']
        })
    
    print(f"Playlist: {concise_data['playlist_name']}")
    print(f"Owner: {concise_data['owner']}")
    print(f"Total tracks: {concise_data['total_tracks']}\n")
    
    return concise_data


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Spotify playlist data and save as JSON"
    )
    parser.add_argument(
        "--playlist",
        required=True,
        help="Spotify playlist URL, URI, or ID"
    )
    parser.add_argument(
        "--output",
        default="playlist_data.json",
        help="Output JSON file (default: playlist_data.json)"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty print the JSON output"
    )
    
    args = parser.parse_args()
    
    # Fetch playlist data
    playlist_data = get_playlist_data(args.playlist)
    
    # Save to file
    with open(args.output, 'w', encoding='utf-8') as f:
        if args.pretty:
            json.dump(playlist_data, f, indent=2, ensure_ascii=False)
        else:
            json.dump(playlist_data, f, ensure_ascii=False)
    
    print(f"✅ Playlist data saved to: {args.output}")
    print(f"   File size: {os.path.getsize(args.output):,} bytes")


if __name__ == "__main__":
    main()
