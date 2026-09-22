"""
freesound_counts.py
Asks Freesound how many CC0 / CC BY sounds match each search word, so you know
which searches are worth harvesting, and which ones need more than one page.

Run:  python freesound_counts.py
"""

import time

import requests

from config import require_secret

# Import rather than copy. One list, one place to change it, no drift between scripts.
from sawt_harvester import FREESOUND_SEARCHES

PAGE_SIZE = 150          # Freesound's maximum results per page
OPEN_ONLY = 'license:("Creative Commons 0" OR "Attribution")'

token = require_secret("FREESOUND_TOKEN")
# Header auth, not ?token=. See freesound_headers() in sawt_harvester.py for why.
HEADERS = {"User-Agent": "SawtHarvester/0.2 (Sawt heritage map research)",
           "Authorization": f"Token {token}"}

print(f"{'word':>16}  {'open hits':>9}  {'pages':>5}")
print("-" * 36)

total = 0
for search in FREESOUND_SEARCHES:
    word = search["query"]
    # Same phrase-quoting rule as the harvester: an unquoted multi-word query returns 0.
    params = {
        "query": f'"{word}"' if " " in word else word,
        "page_size": "1",     # we only want the total, so ask for a single result
        "filter": OPEN_ONLY,
    }
    response = requests.get("https://freesound.org/apiv2/search/text/",
                            params=params, headers=HEADERS, timeout=30)
    if response.status_code != 200:
        print(f"{word:>16}  request failed: {response.status_code} {response.text[:80]}")
        continue

    count = response.json().get("count", 0)
    total += count
    # -(-a // b) is the integer "round up" trick: 151 results over 150 per page = 2 pages.
    pages = -(-count // PAGE_SIZE)
    flag = "  <- needs paging" if pages > 1 else ""
    if search.get("category") == "recitation":
        flag += "  [quarantined]"
    print(f"{word:>16}  {count:>9}  {pages:>5}{flag}")
    time.sleep(0.5)          # be polite to the API

print("-" * 36)
print(f"{'TOTAL':>16}  {total:>9}   (before de-duplication)")
