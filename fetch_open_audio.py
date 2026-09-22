"""
fetch_open_audio.py
Self-host the Commons and archive.org audio, so rule 10 holds for every track.

The Freesound downloader needed OAuth2 and lived inside a 500-a-day quota. These two
need neither: both serve their files from ordinary public URLs. What they do ask for
is politeness, and Wikimedia in particular will start refusing a client that hammers
it or does not say who it is.

Run:  python fetch_open_audio.py            (dry run: shows what it would fetch)
      python fetch_open_audio.py --write
"""

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

import requests

from config import keep_awake

SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"
AUDIO_DIR = SCRIPT_DIR / "sawt_audio"

HEADERS = {"User-Agent": "SawtHarvester/0.3 (Sawt heritage sound map; hazkhan2001@gmail.com)"}
# Wikimedia rate-limits harder than archive.org, and a 429 from them is easy to earn.
PACE = {"commons": 1.5, "archive.org": 0.6}


def safe_name(text: str, fallback: str) -> str:
    """A filename that will survive Windows, Linux and a URL, from any script."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._")
    return (cleaned or fallback)[:70]


def fetch(url: str, target: Path) -> tuple[bool, str]:
    partial = target.with_suffix(target.suffix + ".part")
    try:
        r = requests.get(url, headers=HEADERS, timeout=(10, 30), stream=True)
        if r.status_code != 200:
            return False, f"{r.status_code} {r.reason}"
        with open(partial, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        partial.rename(target)          # rename last: never leave a half file looking whole
        return True, f"{target.stat().st_size / 1_048_576:.2f}MB"
    except requests.RequestException as err:
        partial.unlink(missing_ok=True)
        return False, type(err).__name__


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Commons and archive.org audio.")
    parser.add_argument("--write", action="store_true", help="actually download")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--all", action="store_true",
                        help="fetch every harvested item, not only the ones you approved")
    args = parser.parse_args()

    items = json.loads(CANDIDATES.read_text(encoding="utf-8"))

    # Default to the approved set. Downloading 256 files to ship 37 is the same
    # mistake as reviewing 528 to ship 231: effort spent on material already rejected.
    approved_urls = set()
    approved_path = SCRIPT_DIR / "sawt_approved.json"
    if approved_path.exists() and not args.all:
        approved_urls = {c["page_url"]
                         for c in json.loads(approved_path.read_text(encoding="utf-8"))}

    todo = []
    for c in items:
        if c["source"] not in ("commons", "archive.org"):
            continue
        if approved_urls and c["page_url"] not in approved_urls:
            continue
        if c.get("web_audio") or c.get("local_audio"):
            continue                    # already ours
        url = c.get("audio_url") or ""
        if not url.startswith("http") or not c.get("playable"):
            continue
        suffix = Path(url.split("?")[0]).suffix.lower() or ".ogg"
        name = safe_name(Path(url.split("?")[0]).stem, c["source"]) + suffix
        todo.append((c, url, name))

    print(f"{len(todo)} recordings to self-host "
          f"({sum(1 for c, _, _ in todo if c['source'] == 'commons')} Commons, "
          f"{sum(1 for c, _, _ in todo if c['source'] == 'archive.org')} archive.org)")

    if not args.write:
        for c, url, name in todo[:8]:
            print(f"  [{c['source']}] {name[:52]:<52} {c['title'][:34]}")
        print(f"\nDry run. Add --write to download.")
        return

    keep_awake("the download")
    AUDIO_DIR.mkdir(exist_ok=True)
    if args.limit:
        todo = todo[:args.limit]
    ok = failed = 0
    for index, (c, url, name) in enumerate(todo, start=1):
        target = AUDIO_DIR / name
        if target.exists() and target.stat().st_size > 1024:
            c["local_audio"] = str(Path("sawt_audio") / name).replace("\\", "/")
            continue
        print(f"  [{index}/{len(todo)}] .... {name[:46]}", end="", flush=True)
        success, message = fetch(url, target)
        print(f"  ->  {message}", flush=True)
        if success:
            ok += 1
            c["local_audio"] = str(Path("sawt_audio") / name).replace("\\", "/")
        else:
            failed += 1
        time.sleep(PACE.get(c["source"], 1.0))
        if index % 20 == 0:
            CANDIDATES.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    CANDIDATES.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{ok} downloaded, {failed} failed.")
    print("Next: python make_web_audio.py   (turns these into streaming copies)")


if __name__ == "__main__":
    main()
