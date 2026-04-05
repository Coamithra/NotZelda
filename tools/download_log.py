#!/usr/bin/env python3
"""
Fetch and clear the event log from the NotZelda server.
Saves the log locally as log_YYYYMMDD_HHMMSS.txt, then clears the server log.

Usage:
  python download_log.py                          # uses live Hetzner server
  python download_log.py http://localhost:8080    # use local dev server
"""

import base64
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

SERVER = sys.argv[1] if len(sys.argv) > 1 else "http://46.225.218.207:8080"

# Build Basic Auth header from ADMIN_PASSWORD env var
admin_pw = os.environ.get("ADMIN_PASSWORD", "")
auth_headers = {}
if admin_pw:
    creds = base64.b64encode(f"admin:{admin_pw}".encode()).decode()
    auth_headers["Authorization"] = f"Basic {creds}"
else:
    print("Warning: ADMIN_PASSWORD not set — requests may fail with 401/404.")

print(f"Fetching log from {SERVER}/get-log ...")
try:
    req = urllib.request.Request(f"{SERVER}/get-log", headers=auth_headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = resp.read().decode()
except urllib.error.HTTPError as e:
    if e.code == 401:
        print("Error: 401 Unauthorized — check ADMIN_PASSWORD env var.")
    elif e.code == 404:
        print("Error: 404 Not Found — ADMIN_PASSWORD may not be set on the server.")
    else:
        print(f"Error: {e}")
    sys.exit(1)
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

print("Clearing server log ...")
try:
    req = urllib.request.Request(f"{SERVER}/clear-log", headers=auth_headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(resp.read().decode())
except urllib.error.HTTPError as e:
    if e.code == 401:
        print("Warning: could not clear log — 401 Unauthorized, check ADMIN_PASSWORD.")
    elif e.code == 404:
        print("Warning: could not clear log — 404, ADMIN_PASSWORD may not be set on server.")
    else:
        print(f"Warning: could not clear log: {e}")
except Exception as e:
    print(f"Warning: could not clear log: {e}")
