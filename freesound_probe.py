"""
freesound_probe.py
Why did "call to prayer" return 0 hits when the harvest is full of call-to-prayer sounds?

When an API gives an answer you don't believe, the move is not to guess. It is to ask
the same question several slightly different ways and compare. That is what this does.

Run:  python freesound_probe.py
"""

import time

import requests

from config import require_secret

token = require_secret("FREESOUND_TOKEN")
HEADERS = {"User-Agent": "SawtHarvester/0.2 (Sawt heritage map research)",
           "Authorization": f"Token {token}"}
URL = "https://freesound.org/apiv2/search/text/"
OPEN_ONLY = 'license:("Creative Commons 0" OR "Attribution")'

# Each row: a label for the printout, and the parameters to send.
TRIALS = [
    ("bare multi-word",        {"query": "call to prayer", "filter": OPEN_ONLY}),
    ("quoted phrase",          {"query": '"call to prayer"', "filter": OPEN_ONLY}),
    ("no license filter",      {"query": "call to prayer"}),
    ("quoted, no filter",      {"query": '"call to prayer"'}),
    ("single word control",    {"query": "prayer", "filter": OPEN_ONLY}),
    ("field search on name",   {"filter": f'name:"call to prayer" {OPEN_ONLY}'}),
    ("tag search",             {"filter": f'tag:calltoprayer {OPEN_ONLY}'}),
    ("adhan control",          {"query": "adhan", "filter": OPEN_ONLY}),
]

print(f"{'trial':>22}  {'hits':>6}   first result")
print("-" * 78)

for label, extra in TRIALS:
    params = {"page_size": "1", "fields": "name", **extra}
    response = requests.get(URL, params=params, headers=HEADERS, timeout=30)
    if response.status_code != 200:
        print(f"{label:>22}  {response.status_code} {response.text[:50]}")
        continue
    data = response.json()
    results = data.get("results", [])
    first = results[0]["name"][:40] if results else ""
    print(f"{label:>22}  {data.get('count', 0):>6}   {first}")
    time.sleep(0.5)

print("\nRead this as: whichever formulation returns sensible hits is the one the")
print("harvester's search word list should be using.")
