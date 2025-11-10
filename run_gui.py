#!/usr/bin/env python3
"""
Quick launcher for the GUI app.
Install dependencies first with: pip install -r requirements.txt

Usage:
    python run_gui.py
"""
import sys

if __name__ == "__main__":
    try:
        import spotipy
        from dotenv import load_dotenv
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("\nPlease install dependencies first:")
        print("  pip install -r requirements.txt")
        sys.exit(1)

    # Import and run the GUI (tkinter is built-in)
    from gui_app import main

    main()
