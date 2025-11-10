#!/usr/bin/env python3
"""
YouTube Audio Downloader GUI

A tkinter-based desktop application for downloading songs from Spotify playlists.
Features a Spotify playlist checker that automatically detects new tracks and downloads them.

Dependencies:
- tkinter (built-in with Python)
- spotipy
- python-dotenv
- yt-dlp
- FFmpeg (system package)
"""

import os
import sys
import threading
import subprocess
import tempfile
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from typing import List, Tuple

# Attempt to import required packages
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing dependency: {str(e)}")
    print("Install required packages with: pip install spotipy python-dotenv yt-dlp")
    sys.exit(1)

# Configuration
SCRIPT_DIR = Path(__file__).parent
PLAYLISTS_DIR = SCRIPT_DIR / "playlists"
ENV_FILE = SCRIPT_DIR / ".env"
CACHE_FILE = SCRIPT_DIR / ".cache_spotify"

TRACK_NAME_COLUMN = "Track Name"
ARTIST_NAME_COLUMN = "Artist Name(s)"

# Load environment variables
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


def read_processed_set(csv_path: str) -> set:
    """Read processed tracks from history CSV."""
    processed = set()
    if not os.path.exists(csv_path):
        return processed

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if (
                not reader.fieldnames
                or TRACK_NAME_COLUMN not in reader.fieldnames
                or ARTIST_NAME_COLUMN not in reader.fieldnames
            ):
                return processed
            for row in reader:
                track = (row.get(TRACK_NAME_COLUMN) or "").strip().lower()
                artist_field = (row.get(ARTIST_NAME_COLUMN) or "").strip()
                first_artist = (
                    artist_field.split(";")[0].strip().lower() if artist_field else ""
                )
                if track and first_artist:
                    processed.add((track, first_artist))
    except Exception:
        pass
    return processed


def extract_playlist_id(playlist_id_or_uri: str) -> str:
    """Extract the playlist ID from a Spotify playlist URL, URI, or ID."""
    if "open.spotify.com" in playlist_id_or_uri:
        parts = playlist_id_or_uri.split("/")
        playlist_part = [p for p in parts if p.strip()][-1]
        return playlist_part.split("?")[0]
    elif "spotify:playlist:" in playlist_id_or_uri:
        return playlist_id_or_uri.split(":")[-1]
    else:
        return playlist_id_or_uri.strip()


def parse_spotify_playlist_with_log(
    playlist_id_or_uri: str, log_func
) -> Tuple[str, List[Tuple[str, str]], str]:
    """Query Spotify playlist and return (playlist_name, list_of_tracks, playlist_id)."""
    try:
        scope = "playlist-read-private"
        redirect_uri = os.environ.get(
            "SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
        )
        cache_path = str(CACHE_FILE)

        auth_manager = SpotifyOAuth(
            scope=scope, redirect_uri=redirect_uri, cache_path=cache_path
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)

        log_func("Connecting to Spotify...")

        playlist_id = extract_playlist_id(playlist_id_or_uri)
        playlist = sp.playlist(playlist_id, fields="name")
        playlist_name = playlist["name"]

        log_func(f"Fetching tracks from: {playlist_name}")

        items = []
        limit = 100
        offset = 0

        while True:
            resp = sp.playlist_items(
                playlist_id,
                offset=offset,
                limit=limit,
                fields="items.track.name,items.track.artists,next,total",
            )
            if not resp or "items" not in resp:
                break
            for it in resp["items"]:
                track = it.get("track")
                if not track:
                    continue
                name = track.get("name") or ""
                artists = track.get("artists") or []
                artist_names = "; ".join(
                    [a.get("name", "").strip() for a in artists if a and a.get("name")]
                )
                if name:
                    items.append((name.strip(), artist_names.strip()))
            if not resp.get("next"):
                break
            offset += limit

        return playlist_name, items, playlist_id

    except Exception as e:
        log_func(f"ERROR: {str(e)}")
        raise


def write_new_csv(
    new_tracks: List[Tuple[str, str]], out_path: str, append: bool = False
) -> None:
    """Write tracks to CSV."""
    fieldnames = [TRACK_NAME_COLUMN, ARTIST_NAME_COLUMN]

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
    """Download a single track using csvDownloader.py."""
    fd, tmp_csv = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        write_new_csv([(track, artist)], tmp_csv)
        csvdownloader_path = SCRIPT_DIR / "csvDownloader.py"
        if not csvdownloader_path.exists():
            return False

        cmd = [sys.executable, str(csvdownloader_path), tmp_csv, output_dir]
        result = subprocess.run(cmd, capture_output=True, text=True)
        success = "✅ Success: Downloaded" in (result.stdout or "")
        return success
    finally:
        try:
            os.unlink(tmp_csv)
        except OSError:
            pass


def process_playlist(playlist_input: str, output_dir: str, log_widget) -> None:
    """Main processing function: fetch playlist, detect new tracks, download them."""

    def log(msg: str):
        """Thread-safe logging to GUI."""
        log_widget.config(state=tk.NORMAL)
        log_widget.insert(tk.END, msg + "\n")
        log_widget.see(tk.END)
        log_widget.config(state=tk.DISABLED)
        log_widget.update()

    try:
        # Ensure playlists directory exists
        PLAYLISTS_DIR.mkdir(exist_ok=True)

        # Fetch playlist
        playlist_name, playlist_tracks, playlist_id = parse_spotify_playlist_with_log(
            playlist_input, log
        )

        history_path = PLAYLISTS_DIR / f"{playlist_id}.csv"
        processed = read_processed_set(str(history_path))

        log(f"Playlist: {playlist_name} (ID: {playlist_id})")
        log(f"Total tracks: {len(playlist_tracks)}")

        # Find new tracks
        new_tracks = []
        for track_name, artist in playlist_tracks:
            track_clean = track_name.strip()
            artist_clean = artist.replace(";", ",").strip()
            key = (track_clean.lower(), artist_clean.split(",")[0].strip().lower())
            if key not in processed:
                new_tracks.append((track_clean, artist_clean))

        if not new_tracks:
            log("✓ No new tracks found.")
            return

        log(f"Found {len(new_tracks)} new track(s):")
        for t, a in new_tracks:
            log(f"  - {a} - {t}")

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        successful_tracks = []
        failed_tracks = []

        for i, (track, artist) in enumerate(new_tracks, 1):
            log(f"\n[{i}/{len(new_tracks)}] Downloading: {artist} - {track}")

            if download_single_track(track, artist, output_dir):
                successful_tracks.append((track, artist))
                write_new_csv([(track, artist)], str(history_path), append=True)
                log(f"✓ Downloaded and added to history")
            else:
                failed_tracks.append((track, artist))
                log(f"✗ Failed to download")

        log("\n=== Summary ===")
        log(f"Successfully downloaded: {len(successful_tracks)}/{len(new_tracks)}")
        if failed_tracks:
            log(f"Failed: {len(failed_tracks)}")

    except Exception as e:
        log_widget.config(state=tk.NORMAL)
        log_widget.insert(tk.END, f"ERROR: {str(e)}\n")
        log_widget.see(tk.END)
        log_widget.config(state=tk.DISABLED)


class YouTubeAudioDownloaderApp:
    """Main tkinter application."""

    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Audio Downloader")
        self.root.geometry("900x700")
        self.root.resizable(True, True)

        # Configure style
        style = ttk.Style()
        style.theme_use("clam")

        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # Title
        title = ttk.Label(
            main_frame, text="YouTube Audio Downloader", font=("Arial", 16, "bold")
        )
        title.grid(row=0, column=0, columnspan=3, pady=10)

        subtitle = ttk.Label(
            main_frame, text="Spotify Playlist Checker & Downloader", font=("Arial", 10)
        )
        subtitle.grid(row=1, column=0, columnspan=3)

        # Playlist input
        ttk.Label(main_frame, text="Spotify Playlist URL/URI/ID:").grid(
            row=3, column=0, sticky=tk.W, pady=(10, 5)
        )
        self.playlist_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.playlist_var, width=60).grid(
            row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5)
        )

        ttk.Label(
            main_frame,
            text="Paste a Spotify playlist link, URI, or ID",
            font=("Arial", 8),
            foreground="gray",
        ).grid(row=5, column=0, columnspan=2, sticky=tk.W)

        # Output directory
        ttk.Label(main_frame, text="Output Directory:").grid(
            row=6, column=0, sticky=tk.W, pady=(15, 5)
        )
        self.output_var = tk.StringVar(value="downloads")
        output_entry = ttk.Entry(main_frame, textvariable=self.output_var, width=45)
        output_entry.grid(row=7, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        ttk.Button(main_frame, text="Browse", command=self.browse_output).grid(
            row=7, column=1, padx=(5, 0)
        )

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=8, column=0, columnspan=3, pady=15)

        ttk.Button(
            button_frame, text="Download New Tracks", command=self.download_tracks
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Settings", command=self.open_settings).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Exit", command=self.root.quit).pack(
            side=tk.LEFT, padx=5
        )

        # Log display
        ttk.Label(main_frame, text="Log:").grid(
            row=9, column=0, sticky=tk.W, pady=(10, 5)
        )
        self.log_widget = scrolledtext.ScrolledText(
            main_frame, height=20, width=100, state=tk.DISABLED
        )
        self.log_widget.grid(
            row=10,
            column=0,
            columnspan=3,
            sticky=(tk.W, tk.E, tk.N, tk.S),
            pady=(0, 10),
        )

        main_frame.rowconfigure(10, weight=1)
        main_frame.columnconfigure(0, weight=1)

    def browse_output(self):
        """Open folder browser dialog."""
        folder = filedialog.askdirectory(title="Select Output Directory")
        if folder:
            self.output_var.set(folder)

    def open_settings(self):
        """Open settings window."""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("500x250")
        settings_window.grab_set()

        frame = ttk.Frame(settings_window, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Spotify API Settings", font=("Arial", 12, "bold")).grid(
            row=0, column=0, columnspan=2, pady=10
        )

        ttk.Label(frame, text="Client ID:").grid(row=1, column=0, sticky=tk.W, pady=5)
        client_id_var = tk.StringVar(value=os.environ.get("SPOTIPY_CLIENT_ID", ""))
        ttk.Entry(frame, textvariable=client_id_var, width=40, show="*").grid(
            row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 0)
        )

        ttk.Label(frame, text="Client Secret:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        client_secret_var = tk.StringVar(
            value=os.environ.get("SPOTIPY_CLIENT_SECRET", "")
        )
        ttk.Entry(frame, textvariable=client_secret_var, width=40, show="*").grid(
            row=2, column=1, sticky=(tk.W, tk.E), padx=(10, 0)
        )

        ttk.Label(frame, text="Redirect URI:").grid(
            row=3, column=0, sticky=tk.W, pady=5
        )
        redirect_uri_var = tk.StringVar(
            value=os.environ.get(
                "SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
            )
        )
        ttk.Entry(frame, textvariable=redirect_uri_var, width=40).grid(
            row=3, column=1, sticky=(tk.W, tk.E), padx=(10, 0)
        )

        ttk.Label(
            frame,
            text="Get credentials from: https://developer.spotify.com/dashboard",
            font=("Arial", 8),
            foreground="gray",
        ).grid(row=4, column=0, columnspan=2, pady=10)

        def save_settings():
            os.environ["SPOTIPY_CLIENT_ID"] = client_id_var.get()
            os.environ["SPOTIPY_CLIENT_SECRET"] = client_secret_var.get()
            os.environ["SPOTIPY_REDIRECT_URI"] = redirect_uri_var.get()

            # Save to .env file
            with open(ENV_FILE, "w") as f:
                f.write(f"SPOTIPY_CLIENT_ID={client_id_var.get()}\n")
                f.write(f"SPOTIPY_CLIENT_SECRET={client_secret_var.get()}\n")
                f.write(f"SPOTIPY_REDIRECT_URI={redirect_uri_var.get()}\n")

            messagebox.showinfo("Success", "Settings saved!")
            settings_window.destroy()

        ttk.Button(frame, text="Save", command=save_settings).grid(
            row=5, column=0, pady=15, padx=5
        )
        ttk.Button(frame, text="Cancel", command=settings_window.destroy).grid(
            row=5, column=1, padx=5
        )

        frame.columnconfigure(1, weight=1)

    def download_tracks(self):
        """Initiate download process."""
        playlist_input = self.playlist_var.get().strip()
        output_dir = self.output_var.get().strip()

        if not playlist_input:
            messagebox.showerror(
                "Input Error", "Please enter a Spotify playlist URL/URI/ID"
            )
            return

        if not output_dir:
            output_dir = "downloads"

        if not os.environ.get("SPOTIPY_CLIENT_ID") or not os.environ.get(
            "SPOTIPY_CLIENT_SECRET"
        ):
            messagebox.showerror(
                "Configuration Error",
                "Spotify credentials not configured. Please click 'Settings' first.",
            )
            return

        self.log_widget.config(state=tk.NORMAL)
        self.log_widget.delete(1.0, tk.END)
        self.log_widget.insert(tk.END, "Starting download process...\n")
        self.log_widget.config(state=tk.DISABLED)

        # Run in a separate thread to avoid freezing the GUI
        thread = threading.Thread(
            target=process_playlist,
            args=(playlist_input, output_dir, self.log_widget),
            daemon=True,
        )
        thread.start()


def main():
    """Launch the application."""
    # Check if required env vars are set
    if not os.environ.get("SPOTIPY_CLIENT_ID") or not os.environ.get(
        "SPOTIPY_CLIENT_SECRET"
    ):
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "Spotify Configuration",
            "Spotify credentials not configured.\n\n"
            "Please click 'Settings' and enter your Spotify API credentials.\n"
            "Get them from: https://developer.spotify.com/dashboard",
        )
        root.destroy()

    root = tk.Tk()
    app = YouTubeAudioDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
