#!/usr/bin/env python3
"""
Compare downloaded songs against playlist CSV to find missing tracks.
"""

import os
import csv
import argparse
from pathlib import Path
from songDownloader import sanitize_filename


def load_playlist_csv(csv_path):
    """Load songs from the playlist CSV"""
    songs = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Support both formats: old format (artist/title/album) and new format (Track Name/Artist Name(s)/Album Name)
            if 'Track Name' in row:
                # New format from Spotify export
                artist_field = row['Artist Name(s)']
                # Extract only the first/main artist (before any separator)
                main_artist = artist_field.split(';')[0].split(',')[0].strip()
                
                songs.append({
                    'artist': main_artist,
                    'title': row['Track Name'],
                    'album': row['Album Name']
                })
            else:
                # Old format from our CSV tracking
                artist_field = row['artist']
                main_artist = artist_field.split(';')[0].split(',')[0].strip()
                
                songs.append({
                    'artist': main_artist,
                    'title': row['title'],
                    'album': row['album']
                })
    return songs


def get_downloaded_files(download_dir):
    """Get set of downloaded m4a filenames (without extension)"""
    downloaded = set()
    for file in Path(download_dir).glob('**/*.m4a'):
        # Get filename without extension
        filename = file.stem
        downloaded.add(filename)
    return downloaded


def find_missing_songs(csv_path, download_dir):
    """Compare CSV against downloaded files and report missing songs"""
    print(f"Reading playlist from: {csv_path}")
    print(f"Checking downloads in: {download_dir}\n")
    
    # Load data
    playlist_songs = load_playlist_csv(csv_path)
    downloaded_files = get_downloaded_files(download_dir)
    
    print(f"Playlist contains: {len(playlist_songs)} songs")
    print(f"Downloaded files: {len(downloaded_files)} m4a files\n")
    
    # Cross off songs that exist in downloads folder
    missing = []
    found = 0
    
    for song in playlist_songs:
        # Generate expected filename (same as download logic)
        safe_artist = sanitize_filename(song['artist'])
        safe_title = sanitize_filename(song['title'])
        expected_filename = f"{safe_artist} - {safe_title}"
        
        if expected_filename in downloaded_files:
            found += 1
        else:
            missing.append({
                'artist': song['artist'],
                'title': song['title'],
                'expected_filename': expected_filename,
                'album': song['album']
            })
    
    # Report results
    print(f"{'='*70}")
    print(f"✅ Successfully downloaded: {found}/{len(playlist_songs)}")
    print(f"❌ Missing/Failed: {len(missing)}/{len(playlist_songs)}")
    print(f"{'='*70}\n")
    
    if missing:
        print(f"MISSING SONGS:\n")
        for i, song in enumerate(missing, 1):
            print(f"{i}. {song['artist']} - {song['title']}")
            print(f"   Expected filename: {song['expected_filename']}.m4a")
            print(f"   Album: {song['album']}\n")
    else:
        print("🎉 All songs from the playlist have been downloaded!")
    
    return missing


def main():
    parser = argparse.ArgumentParser(
        description="Compare playlist CSV with downloaded m4a files to find missing tracks"
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to the playlist CSV file (e.g., playlists/PLAYLIST_ID.csv)"
    )
    parser.add_argument(
        "--download-dir",
        required=True,
        help="Path to the download directory containing m4a files"
    )
    parser.add_argument(
        "--output",
        help="Optional: Save missing songs to a text file"
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.csv):
        print(f"❌ Error: CSV file not found: {args.csv}")
        return
    
    if not os.path.exists(args.download_dir):
        print(f"❌ Error: Download directory not found: {args.download_dir}")
        return
    
    # Find missing songs
    missing = find_missing_songs(args.csv, args.download_dir)
    
    # Optionally save to file
    if args.output and missing:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(f"Missing Songs Report\n")
            f.write(f"{'='*70}\n\n")
            for song in missing:
                f.write(f"{song['artist']} - {song['title']}\n")
                f.write(f"Expected filename: {song['expected_filename']}.m4a\n")
                f.write(f"Album: {song['album']}\n\n")
        print(f"\n📄 Missing songs saved to: {args.output}")


if __name__ == "__main__":
    main()
