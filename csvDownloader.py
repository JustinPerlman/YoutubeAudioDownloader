import csv
import subprocess
import os
import argparse

# --- Configuration ---
# Column headers to read from the CSV file
TRACK_NAME_COLUMN = "Track Name"
ARTIST_NAME_COLUMN = "Artist Name(s)"


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download audio tracks from YouTube based on a CSV file containing track information."
    )
    parser.add_argument(
        "csv_file", help="Path to the input CSV file containing track information"
    )
    parser.add_argument(
        "output_dir", help="Directory where the downloaded audio files will be saved"
    )
    return parser.parse_args()


# 1. OPTIONAL: If you still encounter 'Encoder not found' errors,
# set the full path to your FFmpeg executable here. Otherwise, leave it blank.
# Examples:
# Windows: r'C:\Program Files\ffmpeg\bin\ffmpeg.exe'
# macOS/Linux: '/usr/local/bin/ffmpeg'
FFMPEG_PATH = ""

# The base command uses yt-dlp to search YouTube and download the audio.
# -x: extract audio
# --audio-format m4a: set output format to M4A (AAC) to reliably avoid missing MP3 encoder (libmp3lame)
# --audio-quality 0: highest quality available
# ytsearch1: searches YouTube and only uses the first result
YT_DLP_BASE_COMMAND = [
    "yt-dlp",
    "-x",
    "--audio-format",
    "m4a",
    "--audio-quality",
    "0",
    "--quiet",  # Suppress standard output for cleaner terminal
]
# ---------------------


def read_tracks_from_csv(filename):
    """Reads the specified columns from the CSV file and returns a list of dictionaries."""
    tracks = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            # Use csv.DictReader to read rows as dictionaries with column headers as keys
            reader = csv.DictReader(f)

            # Verify required columns exist
            if (
                TRACK_NAME_COLUMN not in reader.fieldnames
                or ARTIST_NAME_COLUMN not in reader.fieldnames
            ):
                print(
                    f"Error: CSV file must contain columns '{TRACK_NAME_COLUMN}' and '{ARTIST_NAME_COLUMN}'."
                )
                return []

            for row in reader:
                track_name = row.get(TRACK_NAME_COLUMN)
                artist = row.get(ARTIST_NAME_COLUMN)

                if track_name and artist:
                    tracks.append(
                        {
                            "artist": artist.split(";")[
                                0
                            ].strip(),  # Take the first artist if multiple are listed (separated by ';')
                            "track": track_name.strip(),
                        }
                    )
                # Skip rows that are missing critical information

    except FileNotFoundError:
        print(f"Error: The input CSV file '{filename}' was not found.")
    except Exception as e:
        print(f"An unexpected error occurred while reading the CSV: {e}")

    return tracks


def main():
    """Reads tracks from a CSV and downloads the corresponding audio from YouTube."""
    # Parse command line arguments
    args = parse_arguments()

    # Prepend FFmpeg location if provided
    current_base_command = list(YT_DLP_BASE_COMMAND)
    if FFMPEG_PATH:
        current_base_command.extend(["--ffmpeg-location", FFMPEG_PATH])
        print(f"Using explicit FFmpeg location: {FFMPEG_PATH}")

    # 1. Load tracks from CSV
    tracks = read_tracks_from_csv(args.csv_file)
    if not tracks:
        print("No tracks loaded. Exiting.")
        return

    # 2. Setup download directory
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        print(f"Created output directory: {args.output_dir}")

    total_tracks = len(tracks)
    print(f"Found {total_tracks} tracks to process from {args.csv_file}.")

    successful_downloads = 0
    failed_downloads = 0

    # 3. Loop through all tracks and download
    for i, track_info in enumerate(tracks):
        artist = track_info["artist"]
        track_name = track_info["track"]

        # Construct the most accurate search query
        search_query = f"{artist} - {track_name}"

        # Define the output filename template
        output_filename_template = os.path.join(
            args.output_dir, f"{artist} - {track_name}.%(ext)s"
        )

        print(f"\n--- [{i+1}/{total_tracks}] Searching for: {search_query} ---")

        # Construct the full command for this track
        command = current_base_command + [
            "-o",
            output_filename_template,
            f"ytsearch1:{search_query}",
        ]

        try:
            # Execute the download command
            subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"✅ Success: Downloaded {track_name}")
            successful_downloads += 1

        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to download/convert for: {search_query}")
            print("   --- YT-DLP ERROR OUTPUT ---")
            # Print stderr for debugging the yt-dlp failure
            print(e.stderr)
            print("   ---------------------------")
            failed_downloads += 1
        except FileNotFoundError:
            # This FileNotFoundError likely means 'yt-dlp' itself is not found
            print(
                "\nFATAL ERROR: 'yt-dlp' command not found. Please ensure yt-dlp is installed and in your system's PATH."
            )
            return

    # 4. Print summary
    print("\n==================================")
    print("Download Process Complete.")
    print(f"Total Tracks Processed: {total_tracks}")
    print(f"Successful Downloads: {successful_downloads}")
    print(f"Failed Downloads: {failed_downloads}")
    print(f"Files are saved in the '{args.output_dir}' directory.")
    print("==================================")


if __name__ == "__main__":
    main()

# To run the script, use the command:
# python csvDownloader.py input.csv output_directory
