"""
commons_geo_probe.py
Why did 217 Commons recordings arrive with no coordinates?

Two possibilities, and guessing between them is how you waste an afternoon:
  (a) our request is wrong and the data is there
  (b) Commons audio files genuinely rarely carry a {{Location}} template

This asks both questions directly. It also tests a third, better idea: instead of
searching by WORD and hoping for coordinates, search by PLACE using Commons'
geosearch, which only ever returns things that have a location.

Run:  python commons_geo_probe.py
"""

import json
import time
from collections import Counter
from pathlib import Path

import requests

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "SawtHarvester/0.3 (Sawt heritage sound map; hazkhan2001@gmail.com)"}
SCRIPT_DIR = Path(__file__).resolve().parent

HUBS = [
    ("Fez", 34.0646, -4.9737), ("Cairo", 30.0444, 31.2357),
    ("Aleppo", 36.2021, 37.1343), ("Konya", 37.8746, 32.4932),
    ("Isfahan", 32.6539, 51.6660), ("Delhi", 28.6139, 77.2090),
    ("Kashgar", 39.4704, 75.9898), ("Istanbul", 41.0082, 28.9784),
    ("Marrakech", 31.6295, -7.9811), ("Baku", 40.4093, 49.8671),
]


def get(params: dict) -> dict:
    r = requests.get(API, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


print("QUESTION 1: do the files we already harvested have coordinates we failed to read?")
path = SCRIPT_DIR / "sawt_candidates.json"
items = json.loads(path.read_text(encoding="utf-8"))
commons_titles = [c["title"] for c in items if c["source"] == "commons"][:40]

# titles= takes up to 50 names at once, separated by "|". One request, forty answers.
data = get({"action": "query", "format": "json",
            "titles": "|".join(f"File:{t}" for t in commons_titles),
            "prop": "coordinates", "coprop": "type|name", "colimit": "max"})
pages = data.get("query", {}).get("pages", {})
with_coords = [p for p in pages.values() if p.get("coordinates")]
print(f"  checked {len(pages)} files, {len(with_coords)} have coordinates")
for p in with_coords[:5]:
    c = p["coordinates"][0]
    print(f"    {p['title'][:55]}  ->  {c['lat']}, {c['lon']}")
if not with_coords:
    print("  Verdict: the data is not there. Commons audio rarely carries {{Location}}.")
else:
    print("  Verdict: the data IS there and our request was wrong. Investigate.")

print("\nQUESTION 2: search by place instead of by word (geosearch, namespace 6)")
print(f"  {'hub':<12} {'files':>6}  {'audio':>6}")
print("  " + "-" * 28)
found_any = []
for name, lat, lng in HUBS:
    try:
        # gsradius is capped at 10000 metres by the API. Small, but city centres are small.
        data = get({"action": "query", "format": "json",
                    "generator": "geosearch", "ggscoord": f"{lat}|{lng}",
                    "ggsradius": "10000", "ggsnamespace": "6", "ggslimit": "50",
                    "prop": "imageinfo", "iiprop": "url|mediatype|mime"})
        pages = data.get("query", {}).get("pages", {})
        audio = [p for p in pages.values()
                 if p.get("imageinfo") and p["imageinfo"][0].get("mediatype") == "AUDIO"]
        print(f"  {name:<12} {len(pages):>6}  {len(audio):>6}")
        for p in audio:
            found_any.append((name, p["title"]))
    except requests.RequestException as err:
        print(f"  {name:<12} failed: {err}")
    time.sleep(0.7)

print()
if found_any:
    print(f"  {len(found_any)} geolocated audio files near the hubs:")
    for hub, title in found_any[:20]:
        print(f"    [{hub}] {title}")
    print("\n  Worth adding geosearch to the harvester as a place-first source.")
else:
    print("  No geolocated audio near any hub. Commons audio is not a geographic source;")
    print("  its recordings will have to be placed by hand or by the gazetteer pass.")
