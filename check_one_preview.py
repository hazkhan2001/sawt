"""
check_one_preview.py
One URL, maximum detail. For when a download hangs and you need to know why.

Run: python check_one_preview.py
"""

import json
import time
from pathlib import Path

import requests

items = json.loads((Path(__file__).resolve().parent / "sawt_candidates.json")
                   .read_text(encoding="utf-8"))
url = next(c["audio_url"] for c in items
           if c["source"] == "freesound" and (c.get("audio_url") or "").startswith("http"))
print("URL:", url, "\n")

for label, headers in [
    ("plain",           {}),
    ("with User-Agent", {"User-Agent": "SawtHarvester/0.3 (Sawt heritage sound map)"}),
    ("browser-like",    {"User-Agent": "Mozilla/5.0", "Referer": "https://freesound.org/"}),
]:
    started = time.monotonic()
    try:
        r = requests.get(url, headers=headers, timeout=(10, 20), stream=True)
        first = next(r.iter_content(chunk_size=8192), b"")
        elapsed = time.monotonic() - started
        print(f"{label:<16} {r.status_code} {r.reason} | "
              f"{r.headers.get('Content-Type')} | "
              f"{r.headers.get('Content-Length')} bytes | "
              f"first chunk {len(first)}B in {elapsed:.1f}s")
        r.close()
    except requests.RequestException as err:
        print(f"{label:<16} {type(err).__name__}: {str(err)[:110]}")
