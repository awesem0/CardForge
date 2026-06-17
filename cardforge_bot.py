#!/usr/bin/env python3
"""
CardForge Bot — Adventure ID Lab
Downloads completed cards from Google Drive and saves them locally for printing.
Mac Automator can watch the output folder and auto-print new arrivals.

Setup:
  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib Pillow
  python3 cardforge_bot.py --auth   # first run: opens browser for OAuth
  python3 cardforge_bot.py          # run normally (polls every 30s)
"""

import os
import sys
import time
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DRIVE_FOLDER_ID   = 'YOUR_GOOGLE_DRIVE_FOLDER_ID'   # Drive folder where GAS saves cards
OUTPUT_DIR        = Path.home() / 'Desktop' / 'CardForge_Orders'
CREDENTIALS_FILE  = Path(__file__).parent / 'credentials.json'  # OAuth2 client secret
TOKEN_FILE        = Path(__file__).parent / 'token.json'
POLL_INTERVAL_SEC = 30
AUTO_PRINT        = False   # Set True to auto-send to default printer
CARD_SIZE_IN      = (2.125, 3.375)  # inches (54×86mm Pokemon card size)
# ──────────────────────────────────────────────────────────────────────────────

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


def get_drive_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"❌ credentials.json not found at {CREDENTIALS_FILE}")
                print("   Download it from Google Cloud Console > APIs & Services > Credentials")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    return build('drive', 'v3', credentials=creds)


def list_new_files(service, known_ids):
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='image/png' and trashed=false",
        fields="files(id, name, createdTime, size)",
        orderBy="createdTime desc",
        pageSize=50,
    ).execute()
    return [f for f in results.get('files', []) if f['id'] not in known_ids]


def download_file(service, file_id, dest_path):
    from googleapiclient.http import MediaIoBaseDownload
    import io

    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    dest_path.write_bytes(buf.getvalue())


def print_card(path):
    """Send to default printer at correct card dimensions (Mac lpr)."""
    dpi = 300
    w_px = int(CARD_SIZE_IN[0] * dpi)
    h_px = int(CARD_SIZE_IN[1] * dpi)
    cmd = [
        'lpr',
        '-o', f'media=Custom.{w_px}x{h_px}pt',
        '-o', 'fit-to-page',
        str(path),
    ]
    subprocess.run(cmd, check=True)
    print(f"   🖨  Sent to printer: {path.name}")


def run_bot():
    print("🃏 CardForge Bot — Adventure ID Lab")
    print(f"   Watching Drive folder: {DRIVE_FOLDER_ID}")
    print(f"   Saving to: {OUTPUT_DIR}")
    print(f"   Auto-print: {'YES' if AUTO_PRINT else 'NO'}")
    print(f"   Polling every {POLL_INTERVAL_SEC}s  (Ctrl-C to stop)\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    state_file = OUTPUT_DIR / '.downloaded_ids.json'
    known_ids = set(json.loads(state_file.read_text()) if state_file.exists() else [])

    service = get_drive_service()

    while True:
        try:
            new_files = list_new_files(service, known_ids)
            if new_files:
                for f in new_files:
                    name = f['name']
                    dest = OUTPUT_DIR / name
                    print(f"⬇  Downloading: {name}")
                    download_file(service, f['id'], dest)
                    known_ids.add(f['id'])
                    state_file.write_text(json.dumps(list(known_ids)))
                    print(f"   ✅ Saved: {dest}")
                    if AUTO_PRINT:
                        print_card(dest)
            else:
                ts = datetime.now().strftime('%H:%M:%S')
                print(f"[{ts}] No new cards.", end='\r')
        except KeyboardInterrupt:
            print("\n👋 Bot stopped.")
            break
        except Exception as e:
            print(f"\n⚠  Error: {e}")

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CardForge Drive polling bot')
    parser.add_argument('--auth', action='store_true', help='Re-authenticate Google Drive OAuth')
    args = parser.parse_args()

    if args.auth:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        print("🔑 Opening browser for Google Drive authentication...")
        get_drive_service()
        print("✅ Authentication saved to token.json")
    else:
        run_bot()
