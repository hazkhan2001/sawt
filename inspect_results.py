"""
inspect_results.py
Summarises sawt_candidates.json so you can see what the harvester found.
Run it after sawt_harvester.py:  python inspect_results.py
"""

import argparse
import json
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser(description="Summarise a harvest result file.")
parser.add_argument("--preview", action="store_true",
                    help="read sawt_candidates_preview.json instead of the real results")
args = parser.parse_args()

# Look for the JSON next to this script, wherever the terminal is.
name = "sawt_candidates_preview.json" if args.preview else "sawt_candidates.json"
path = Path(__file__).resolve().parent / name
if not path.exists():
    raise SystemExit(f"No results yet. Run sawt_harvester.py first (looked for {path}).")

print(f"Reading {path.name}\n")

items = json.loads(path.read_text(encoding="utf-8"))
print(f"{len(items)} candidates\n")

# Counter counts how often each value (here, each pair) appears.
print("Tier x playable:", dict(Counter((c["tier"], c["playable"]) for c in items)))
print("Source x tier:  ", dict(Counter((c["source"], c["tier"]) for c in items)))

print("\nTier B licenses:")
for license_name, count in Counter(c["license"] for c in items if c["tier"] == "B").most_common():
    print(f"  {count:>3}  {license_name}")

print("\nWhy files are not playable:")
# Two for clauses read like nested loops: for each failed candidate, for each of its notes.
# Keep the whole note now that it carries the HTTP status, not just the label before ":".
reasons = Counter(n for c in items if not c["playable"] for n in c["notes"]
                  if n.startswith(("Not playable", "Resolver error", "File not found",
                                   "Freesound returned no previews")))
for reason, count in reasons.most_common():
    print(f"  {count:>3}  {reason}")

# Recitation is held apart on purpose (spec section 8). It must never appear in a
# list headed "ready to use" for the music pool, so it is filtered out here and
# counted separately.
recitation = [c for c in items if c.get("category") == "recitation"]
if recitation:
    playable_recitation = sum(1 for c in recitation if c["playable"])
    print(f"\nQuarantined recitation: {len(recitation)} ({playable_recitation} playable)")
    print("  Held for spec task 4. Not part of the music pool.")

# The number that actually decides whether Sawt can exist: a recording with no
# coordinates cannot be placed on a globe, however good its license is.
placeable = [c for c in items
             if c["tier"] == "A" and c.get("category") != "recitation"
             and c.get("lat") is not None and c.get("lng") is not None]
tier_a_music = [c for c in items if c["tier"] == "A" and c.get("category") != "recitation"]
print(f"\nTier A, not recitation:     {len(tier_a_music)}")
print(f"  of those, geolocated:     {len(placeable)}  <- can be placed on the globe")
print(f"  of those, no coordinates: {len(tier_a_music) - len(placeable)}")
print("  coordinates by source:")
for src in sorted({c["source"] for c in tier_a_music}):
    total = [c for c in tier_a_music if c["source"] == src]
    with_geo = [c for c in total if c.get("lat") is not None]
    print(f"    {src:<12} {len(with_geo):>4} of {len(total):>4}")

ready = [c for c in items
         if c["tier"] == "A" and c["playable"] and c.get("category") != "recitation"]
print(f"\nReady to use (Tier A, playable, not recitation): {len(ready)}")

# Which search found each one: a bad search term shows up here as a cluster of junk.
by_search = Counter(c.get("found_by") or c["source"] for c in ready)
print("Found by:")
for name, count in by_search.most_common():
    print(f"  {count:>4}  {name}")
