"""
diagnose_playable.py
Asks each failing audio URL what actually went wrong, instead of just "not playable".

check_playable() in the harvester answers True or False. That is all a harvest run
needs, but it throws away the reason. This script keeps the reason.

Run after sawt_harvester.py:  python diagnose_playable.py
"""

import json
import time
from collections import Counter
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"

# Wikimedia asks that automated clients identify themselves with a way to be contacted.
# A vague User-Agent is a common reason their servers return 403.
HEADERS = {"User-Agent": "SawtHarvester/0.2 (Sawt heritage map research; hazkhan2001@gmail.com)"}


def probe(url: str) -> dict:
    """One URL in, one small report out. Never raises: errors become part of the report."""
    report = {"url": url, "method": "HEAD", "status": None,
              "content_type": None, "error": None}
    try:
        r = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if r.status_code in (403, 405):
            # Some servers refuse HEAD outright. Ask for a single byte instead.
            report["method"] = "GET range"
            r = requests.get(url, headers={**HEADERS, "Range": "bytes=0-0"},
                             timeout=20, stream=True)
            r.close()                      # we asked for one byte, do not hold the socket open
        if r.status_code == 429:
            # We caused this by asking too fast. Wait and ask once more before judging.
            time.sleep(float(r.headers.get("Retry-After", 0)) or 5.0)
            r = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
            report["method"] += " (retried after 429)"
        report["status"] = r.status_code
        report["content_type"] = r.headers.get("Content-Type")
    except requests.RequestException as err:
        # type(err).__name__ gives the class name, e.g. "ConnectionError" or "Timeout".
        report["error"] = f"{type(err).__name__}: {err}"
    return report


def main() -> None:
    if not CANDIDATES.exists():
        raise SystemExit(f"No results yet. Run sawt_harvester.py first (looked for {CANDIDATES}).")

    items = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    failing = [c for c in items if not c["playable"] and c["audio_url"]
               and not str(c["audio_url"]).startswith(("C:", "/", "sawt_local_audio"))]
    missing = [c for c in items if not c["playable"] and not c["audio_url"]]

    print(f"{len(failing)} candidates have a URL that failed the playable check.")
    print(f"{len(missing)} candidates never got a URL at all (a resolver problem, not a server one).\n")

    verdicts = Counter()
    for c in failing:
        r = probe(c["audio_url"])
        # A short label so the Counter at the end groups like with like.
        if r["error"]:
            verdict = r["error"].split(":")[0]
        else:
            verdict = f"{r['status']} {r['content_type']}"
        verdicts[verdict] += 1
        print(f"  [{c['source']:>11}] {verdict:<34} {r['method']:<9} {c['title'][:42]}")
        time.sleep(1.5)          # slower than the harvester: these hosts rate-limit

    print("\nGrouped:")
    for verdict, n in verdicts.most_common():
        print(f"  {n:>3}  {verdict}")

    if missing:
        print("\nNo URL resolved for:")
        for c in missing:
            reason = next((n for n in c["notes"] if "error" in n.lower()
                           or "no previews" in n.lower()), "no reason recorded")
            print(f"  [{c['source']}] {c['title'][:45]:<45} {reason[:70]}")


if __name__ == "__main__":
    main()
