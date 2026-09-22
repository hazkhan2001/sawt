"""
fetch_attribution.py
Find the missing credit lines that CC BY and CC BY-SA require.

Attribution under those licences is a CONDITION, not a courtesy: publishing without
it is infringement, which is why build_site_data.py refuses such a record outright.

The names are not lost, only unfetched. The harvester asked Commons and archive.org
for a licence and a URL and never asked who made the recording. Both will tell us,
from public endpoints, no key needed:

    archive.org   /metadata/<id>  ->  metadata.creator, or the uploader
    Commons       imageinfo extmetadata.Artist  (HTML, so tags have to come out)

Run:  python fetch_attribution.py            (dry run)
      python fetch_attribution.py --write
"""

import argparse
import json
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import unquote

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"
REVIEWS = SCRIPT_DIR / "sawt_reviews.json"
HEADERS = {"User-Agent": "SawtHarvester/0.3 (Sawt heritage sound map; hazkhan2001@gmail.com)"}


def strip_html(value: str) -> str:
    """Commons returns Artist as a fragment of HTML, often a link. We want the text."""
    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(unescape(text).split())


def archive_creator(page_url: str) -> str:
    identifier = page_url.rstrip("/").split("/details/")[-1]
    data = requests.get(f"https://archive.org/metadata/{identifier}",
                        headers=HEADERS, timeout=30).json()
    meta = data.get("metadata", {})
    for key in ("creator", "artist", "uploader"):
        value = meta.get(key)
        if value:
            # Some fields come back as a list when an item has several creators.
            return ", ".join(value) if isinstance(value, list) else str(value)
    return ""


def commons_artist(page_url: str) -> str:
    title = unquote(page_url.split("/wiki/")[-1])
    data = requests.get("https://commons.wikimedia.org/w/api.php", headers=HEADERS, timeout=30,
                        params={"action": "query", "format": "json", "titles": title,
                                "prop": "imageinfo", "iiprop": "extmetadata"}).json()
    page = next(iter(data.get("query", {}).get("pages", {}).values()), {})
    meta = (page.get("imageinfo") or [{}])[0].get("extmetadata", {})
    for key in ("Artist", "Attribution", "Credit"):
        if meta.get(key, {}).get("value"):
            return strip_html(meta[key]["value"])
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch missing CC BY credit lines.")
    parser.add_argument("--write", action="store_true", help="save the names found")
    parser.add_argument("--all", action="store_true",
                        help="not just the approved set")
    args = parser.parse_args()

    items = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    reviews = json.loads(REVIEWS.read_text(encoding="utf-8")) if REVIEWS.exists() else {}
    approved = {c["page_url"] for c in items
                if reviews.get(c["page_url"], {}).get("decision") == "approve"}

    need = []
    for c in items:
        if not args.all and c["page_url"] not in approved:
            continue
        lic = (c.get("license") or "").lower()
        if "by" not in lic.replace("-", " ").split() and not lic.startswith("cc by"):
            continue
        if (c.get("attribution") or "").strip():
            continue
        need.append(c)

    print(f"{len(need)} records need a credit line.\n")
    found = missing = 0
    for index, c in enumerate(need, start=1):
        try:
            name = (archive_creator(c["page_url"]) if c["source"] == "archive.org"
                    else commons_artist(c["page_url"]) if c["source"] == "commons" else "")
        except (requests.RequestException, ValueError, KeyError) as err:
            name = ""
            print(f"  [{index}/{len(need)}] ERROR {type(err).__name__}  {c['title'][:44]}")
            continue
        if name:
            found += 1
            print(f"  [{index}/{len(need)}] {name[:34]:<34} <- {c['title'][:40]}")
            if args.write:
                c["attribution"] = name
        else:
            missing += 1
            print(f"  [{index}/{len(need)}] (no creator field)  {c['title'][:40]}")
        time.sleep(0.8)

    print(f"\n{found} credit lines found, {missing} with nothing recorded upstream.")
    if missing:
        print("  Those need a human look at the source page, or dropping. A CC BY work")
        print("  whose author is genuinely unrecorded cannot be lawfully republished.")
    if not args.write:
        print("\nDry run. Add --write to save these into sawt_candidates.json.")
        return
    CANDIDATES.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved. Re-run build_site_data.py.")


if __name__ == "__main__":
    main()
