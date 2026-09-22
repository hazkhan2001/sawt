"""
prune.py
Remove junk from an existing results file, without re-running the 30 minute harvest.

Currently removes Wikimedia dictionary pronunciation clips, which are one person
saying one word into a laptop mic to illustrate a Wiktionary entry. They match every
search term and are not recordings of anywhere.

Run:  python prune.py            (dry run)
      python prune.py --apply    (rewrites sawt_candidates.json, keeping a .bak)
"""

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from sawt_harvester import is_pronunciation_clip

SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Strip junk entries from harvest results.")
    parser.add_argument("--apply", action="store_true", help="actually rewrite the file")
    args = parser.parse_args()

    if not CANDIDATES.exists():
        raise SystemExit(f"No results at {CANDIDATES}.")
    items = json.loads(CANDIDATES.read_text(encoding="utf-8"))

    junk = [c for c in items if is_pronunciation_clip(c["title"])]
    keep = [c for c in items if not is_pronunciation_clip(c["title"])]

    print(f"{len(items)} candidates, {len(junk)} are dictionary pronunciation clips.")
    print("by source:", dict(Counter(c["source"] for c in junk)))
    print("by search term that found them:")
    for term, n in Counter(c.get("found_by") or "?" for c in junk).most_common(8):
        print(f"  {n:>4}  {term}")

    if not args.apply:
        print(f"\nDry run. Would keep {len(keep)}. Re-run with --apply to rewrite.")
        return

    # Keep a copy. An irreversible cleanup of a 30 minute harvest is not a cleanup.
    shutil.copy2(CANDIDATES, CANDIDATES.with_suffix(".json.bak"))
    CANDIDATES.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nKept {len(keep)}. Previous file saved as {CANDIDATES.name}.bak")


if __name__ == "__main__":
    main()
