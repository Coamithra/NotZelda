#!/usr/bin/env python3
"""
Fetch and clear the event log from the NotZelda server.
Saves the log locally as log_YYYYMMDD_HHMMSS.txt

Usage:
  python download_log.py                          # uses live Hetzner server
  python download_log.py http://localhost:8080    # use local dev server
"""

import sys
import urllib.request
from datetime import datetime
from pathlib import Path

SERVER = sys.argv[1] if len(sys.argv) > 1 else "http://46.225.218.207:8080"
url = f"{SERVER}/get-log"

print(f"Fetching log from {url} ...")
try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = resp.read().decode()
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

if not data.strip():
    print("Log is empty — nothing to save.")
    sys.exit(0)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out = Path(f"log_{timestamp}.txt")
out.write_text(data, encoding="utf-8")
print(f"Saved {len(data.splitlines())} lines to {out}")
