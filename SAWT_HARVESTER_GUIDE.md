# Sawt Harvester: Setup and Code Guide

A small Python toolkit that finds openly licensed and public-domain recordings for **Sawt: The Islamic Soundscape Map**, checks their licenses, finds a real playable audio file for each, and saves everything to one JSON file. It also lets you add your own recordings.

The scripts **find** candidates. A human still **confirms** each one before it goes into the app.

---

## 1. Project layout

Put all of these in one folder, for example `sawt-harvester/`:

```
sawt-harvester/
├── sawt_harvester.py       # main script: harvest, classify, resolve audio URLs
├── inspect_results.py      # summarises the output
├── freesound_counts.py     # optional: how many Freesound results exist per word
├── requirements.txt        # the two libraries the scripts need
├── manual_sources.json     # created on first run: describe your own files here
├── sawt_local_audio/       # created on first run: put your own audio files here
└── sawt_candidates.json    # the output, created by sawt_harvester.py
```

Every script finds its files relative to its own location, so you can run them from any folder.

---

## 2. Setup on a new computer

You need Python 3.9 or newer. Check with `python3 --version` (macOS) or `py --version` (Windows).

### macOS

```bash
cd ~/path/to/sawt-harvester
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
cd C:\path\to\sawt-harvester
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**What a virtual environment (`.venv`) is:** a private copy of Python for this project. Libraries you install go inside the project folder instead of your whole computer, so projects can't break each other. You'll see `(.venv)` at the start of your terminal prompt while it's active. Run the `activate` line again each time you open a new terminal.

If Windows blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

---

## 3. Freesound API key (optional but recommended)

Without a key the harvester skips Freesound and prints `No FREESOUND_TOKEN set, skipping Freesound.`

1. Log in at freesound.org, open **freesound.org/apiv2/apply**, and create credentials (any name, e.g. "Sawt harvester, personal research").
2. Copy the value labelled **Client secret/Api key**.
3. Set it as an environment variable:

**macOS, permanently** (the `%` in your prompt means you use zsh, which reads `~/.zshrc`):

```bash
echo 'export FREESOUND_TOKEN="paste_your_key_here"' >> ~/.zshrc
source ~/.zshrc
echo $FREESOUND_TOKEN
```

**Windows, permanently** (then close and reopen the terminal):

```powershell
setx FREESOUND_TOKEN "paste_your_key_here"
```

**Why a variable instead of pasting the key into the code:** if you share the script or upload it to GitHub, the key doesn't travel with it. Treat the key like a password.

---

## 4. Running it

With `.venv` active, inside the project folder:

```bash
python freesound_counts.py    # optional: see how many results each word has
python sawt_harvester.py      # main run, takes a few minutes
python inspect_results.py     # read the summary
```

A successful harvester run ends like this:

```
Tier A: 37
Tier B: 45
Tier C: 22
Playable audio files: 65 of 104
Saved 104 candidates to /.../sawt-harvester/sawt_candidates.json
```

The number that matters most is **Tier A and playable**, which `inspect_results.py` prints as "Ready to use."

---

## 5. Adding your own recordings

1. Run `sawt_harvester.py` once. It creates `sawt_local_audio/` and `manual_sources.json`.
2. Copy your audio into `sawt_local_audio/` (MP3, M4A, AAC, OGG, Opus, WAV, FLAC).
3. In `manual_sources.json`, add one entry per file. Copy the example block, separate blocks with commas, and leave the `EXAMPLE` entry in place (it's skipped).
4. Run the harvester again. It warns about any audio file in the folder without an entry.

What to write in `"license"`:

| Situation | Write | Result |
|---|---|---|
| You recorded it | `"Own recording"` | Tier A, reminder to get consent from anyone audible |
| An ensemble or zawiya agreed | `"Permission from <name>"` | Tier A, reminder to keep the written permission |
| Downloaded under an open license | `"CC BY"`, `"CC0"`, etc. + link in `"source_url"` | Classified like any web source |
| Store-bought, CD rip, saved from YouTube | Don't add it | Can't be published in the app |

---

## 6. Understanding the output

Each item in `sawt_candidates.json` has these fields:

| Field | Meaning |
|---|---|
| `source` | `commons`, `archive.org`, `freesound`, or `local` |
| `title`, `page_url` | What it is and where it lives |
| `license`, `attribution` | Rights information and the credit line (required for CC BY) |
| `year`, `lat`, `lng` | Date and coordinates when known |
| `tier` | **A** open to use, **B** check by hand, **C** non-commercial only |
| `audio_url` | Lightweight streaming file (MP3 preferred) |
| `archival_url` | Best-quality original (FLAC/WAV) for self-hosting |
| `duration_seconds` | Length when known |
| `playable` | `true` once a live check confirmed the file responds |
| `notes` | Warnings and reasons, e.g. why a file isn't playable |

---

## 7. Rights rules the code is built on

Not legal advice; a working summary from the research.

- **US 78rpm cutoff.** Sound recordings published in 1925 or earlier are US public domain. The cutoff moves forward one year each January (1926 recordings open on 1 January 2027), which is why the code uses `date.today().year - 101`.
- **Unpublished field recordings don't get that pass.** Early unpublished recordings (e.g. the 1906–1909 Jeddah cylinders at Leiden) need permission.
- **An archive.org upload is not a license.** Check each item's Usage and Rights fields.
- **A license on a digital transfer is not a license on the recording.** Someone who digitised a 1920s disc can't license a recording they don't own.
- **CC0 labels can be fake.** Skip anything that says it was taken from YouTube.
- **Non-commercial (NC) licenses** stop being usable if the app ever earns money, including ads.
- **Quran recitations** are copyrighted as recordings even though the text isn't. The major sources don't grant redistribution licenses.
- **Self-host** the files you use instead of hotlinking Freesound previews or other people's servers.

---

## 8. Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `OSError: [Errno 30] Read-only file system` | An old version saved relative to the terminal's folder (e.g. `/`) | Use the current script; it saves next to itself |
| `No FREESOUND_TOKEN set, skipping Freesound.` | The environment variable isn't set in this terminal | Section 3, then open a new terminal |
| `NotOpenSSLWarning ... LibreSSL` | macOS system Python uses an older SSL library | Harmless. Using a `.venv` from a newer Python removes it |
| `ModuleNotFoundError: No module named 'requests'` | Libraries not installed in the active Python | Activate `.venv`, run `pip install -r requirements.txt` |
| `Not described in manual_sources.json yet: ...` | An audio file has no JSON entry | Add an entry for it |
| `json.decoder.JSONDecodeError` | Typo in `manual_sources.json`, usually a missing or extra comma | Paste the file into a JSON validator to find the line |
| Many `Resolver error` notes | A site was slow or blocked requests | Run again later; results can vary by run |

---

## 9. Python concepts used (quick reference)

| Concept | Where | What it does |
|---|---|---|
| `@dataclass` | `Candidate` | Writes the setup code for a class that just holds fields; like a TypeScript `interface` |
| `if` / `elif` rules | `classify` | Sort each record into Tier A, B, or C by its license text |
| `re.search(r"\bnc\b", ...)` | `classify` | Regex word boundary: matches "by-nc" but not "once" |
| `while True` + `"continue"` | `fetch_commons_category` | Paging: keep asking the API until no more results |
| `lambda w=word:` | `main` | Default argument captures each loop value now, not after the loop ends |
| Priority nested loops | `pick_file` | Outer loop = your preference order, so the best format wins |
| `quote()` / `unquote()` | resolvers | Make spaces and Arabic letters URL-safe, and back |
| HEAD request + `Range` fallback | `check_playable` | Check a file exists without downloading it |
| `time.sleep(0.5)` | `resolve_all` | Politeness pause so free archives don't block you |
| `Path(__file__).resolve().parent` | top of each script | Find files next to the script, not the terminal's folder |
| Fail fast with `.touch()` | `main` | Prove you can save before minutes of network work |
| `try` / `except ImportError` | top of harvester | Optional library: use `mutagen` if installed, run fine if not |
| Set difference `a - b` | `load_local` | Files on disk that the JSON doesn't mention |
| Passing `load_local` without `()` | `main` | Hand over the function to run later inside error handling |
| `Counter` | `inspect_results.py` | Count how often each value appears |
| `os.environ.get(...)` | `main` | Read the API key from the environment; `None` if missing |

---

## 10. Full code

### requirements.txt

```text
requests
mutagen
```

### sawt_harvester.py

```python
"""
sawt_harvester.py
Finds openly licensed recordings for the Sawt map and saves them to JSON.

What it does:
  1. Starts from a hand-verified seed list (checked on the web).
  2. Loads your own audio files from sawt_local_audio/ + manual_sources.json.
  3. Asks public APIs for more candidates, keeping license data:
       - Wikimedia Commons (categories of files)
       - radio aporee on archive.org (geotagged field recordings)
       - Freesound (needs a free API key in FREESOUND_TOKEN)
  4. Sorts every result into a tier (A open, B check by hand, C non-commercial).
  5. Finds a real, playable audio file for each one.

Run:    pip install -r requirements.txt
        python sawt_harvester.py
Output: sawt_candidates.json (saved next to this script)

The script FINDS candidates. A human still CONFIRMS each one before it ships.
"""

import json
import os
import re
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import date
from typing import Optional

import requests

# Optional extra: `pip install mutagen` lets the script read each local file's length.
# try/except ImportError means the script still runs fine without it.
try:
    from mutagen import File as MutagenFile
except ImportError:
    MutagenFile = None
from urllib.parse import quote, unquote

# US public-domain cutoff for published recordings: 1925 in 2026, 1926 in 2027.
CUTOFF_YEAR = date.today().year - 101
OPEN_LICENSES = ("cc0", "public domain", "pdm", "cc by", "cc-by", "attribution")
# Save next to this script, wherever you run it from.
# __file__ is this script's own path; .parent is the folder containing it.
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = SCRIPT_DIR / "sawt_candidates.json"

# Your own files: drop audio in this folder and describe each one in the JSON file.
LOCAL_DIR = SCRIPT_DIR / "sawt_local_audio"
MANUAL_PATH = SCRIPT_DIR / "manual_sources.json"
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
HEADERS = {"User-Agent": "SawtHarvester/0.1 (personal research project)"}


@dataclass
class Candidate:
    source: str
    title: str
    page_url: str
    license: str = "unknown"
    year: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    attribution: Optional[str] = None
    tier: str = "unsorted"
    notes: list[str] = field(default_factory=list)
    # Filled in by the resolver step: the file the <audio> player actually loads.
    audio_url: Optional[str] = None       # streaming copy (MP3 preferred)
    audio_format: Optional[str] = None
    archival_url: Optional[str] = None    # best-quality original (FLAC/WAV) for self-hosting
    duration_seconds: Optional[float] = None
    playable: Optional[bool] = None       # True once a live check confirms the file responds


# Manually verified during research. Tier "A" means license seen on the page.
VERIFIED_SEED = [
    Candidate("freesound", "Naqshbandi zikr 'Asiklar', Bursa Halilurrahman Dergah",
              "https://freesound.org/people/nesibe/sounds/171928/", "CC0", tier="A"),
    Candidate("freesound", "Naqshbandi Haqqani zikr ceremony, Turkey (8:58)",
              "https://freesound.org/people/nesibe/sounds/171927/", "CC0", tier="A"),
    Candidate("freesound", "Sufi song 'Oyle bir bakisin var ki', Halilurrahman Monchengladbach",
              "https://freesound.org/people/nesibe/sounds/183939/", "CC BY 3.0",
              attribution="nesibe", tier="A"),
    Candidate("archive.org", "Afternoon adhan over Fes el-Bali",
              "https://archive.org/details/aporee_23335_27099", "Public Domain Mark",
              year=2014, lat=34.06657, lng=-4.98106, tier="A"),
    Candidate("freesound", "Adhan, Aroumd, High Atlas",
              "https://freesound.org/people/iainmccurdy/sounds/807484/", "CC BY",
              year=2025, attribution="iainmccurdy", tier="A"),
    Candidate("freesound", "Muezzin, Marrakech",
              "https://freesound.org/people/florianreichelt/sounds/469702/", "CC0", tier="A"),
    Candidate("freesound", "Maghrib adhan, Jemaa el-Fna",
              "https://freesound.org/people/Redalemage/sounds/583206/", "CC0", tier="A"),
    Candidate("freesound", "Isha adhan, Sultanahmet, Istanbul",
              "https://freesound.org/people/volivieri/sounds/161185/", "CC BY",
              year=2012, attribution="volivieri", tier="A"),
    Candidate("freesound", "Dhuhr adhan, Hamtramck, Michigan (96k/24-bit)",
              "https://freesound.org/people/RJStefanski/sounds/255231/", "CC BY",
              attribution="RJStefanski", tier="A"),
    Candidate("commons", "Call to prayer from the Prophet's Mosque, Medina (3:07)",
              "https://commons.wikimedia.org/wiki/File:33937_ejaz215_call-to-prayer-from-the-prophet-s-mo.ogg",
              "CC BY 3.0", attribution="ejaz215", tier="A"),
    Candidate("commons", "Beautiful adhan",
              "https://commons.wikimedia.org/wiki/File:Beautiful_adhan.ogg", "CC0", tier="A"),
    Candidate("commons", "Jabbar Garyagdioglu - Manend-Muxalif (mugham, 1906-12 era)",
              "https://commons.wikimedia.org/wiki/File:Cabbar_Qarya%C4%9Fd%C4%B1o%C4%9Flu-Man%C9%99nd-M%C3%BCxalif.ogg",
              "Public Domain Mark", tier="A"),
    Candidate("commons", "Jabbar Garyagdioglu - Qatar (mugham, 1906-12 era)",
              "https://commons.wikimedia.org/wiki/File:Cabbar_Qarya%C4%9Fd%C4%B1o%C4%9Flu_%E2%80%93_Qatar.ogg",
              "Public Domain Mark", tier="A"),
]


def classify(c: Candidate) -> Candidate:
    """Sort a candidate into A (open), B (check date or license) or C (not open)."""
    lic = c.license.lower()
    # \b means "word boundary", so this matches "by-nc" and "nc" but not "once".
    if re.search(r"\bnc\b", lic) or "noncommercial" in lic.replace(" ", ""):
        c.tier = "C"
        c.notes.append("Non-commercial only: unusable if the app ever earns money.")
    elif "own recording" in lic:
        c.tier = "A"
        c.notes.append("Own recording: confirm anyone audible agreed to being published.")
    elif "permission" in lic:
        c.tier = "A"
        c.notes.append("Permission: keep a copy of the written permission with the project.")
    elif any(word in lic for word in OPEN_LICENSES):
        c.tier = "A"
        # A PD tag on an old recording is only safe if the year clears the cutoff.
        # Only historical recordings (up to 1972) need the cutoff test. A PD Mark on a
        # 2014 field recording is the recordist giving their own work away.
        if "public domain" in lic and c.year and CUTOFF_YEAR < c.year < 1972:
            c.tier = "B"
            c.notes.append(f"PD tag, but {c.year} is after the US cutoff ({CUTOFF_YEAR}).")
    else:
        c.tier = "B"
        c.notes.append("License not recognised: open the page and check by hand.")
    if c.tier == "A" and "by" in lic and not c.attribution:
        c.notes.append("CC BY: record the credit line before publishing.")
    return c


def fetch_commons_category(category: str) -> list[Candidate]:
    """Every audio file in a Commons category, with license and date."""
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "format": "json",
        "generator": "categorymembers", "gcmtitle": f"Category:{category}",
        "gcmtype": "file", "gcmlimit": "50",
        "prop": "imageinfo", "iiprop": "url|mediatype|mime|extmetadata",
    }
    found = []
    while True:
        data = requests.get(api, params=params, headers=HEADERS, timeout=30).json()
        for page in data.get("query", {}).get("pages", {}).values():
            info = page["imageinfo"][0]
            if info.get("mediatype") != "AUDIO":
                continue  # categories also hold photos, skip them
            meta = info.get("extmetadata", {})
            year_text = meta.get("DateTimeOriginal", {}).get("value", "")
            year_match = re.search(r"(18|19|20)\d{2}", year_text)
            found.append(Candidate(
                source="commons",
                title=page["title"].removeprefix("File:"),
                page_url=info["descriptionurl"],
                license=meta.get("LicenseShortName", {}).get("value", "unknown"),
                year=int(year_match.group()) if year_match else None,
                audio_url=info["url"],        # direct upload.wikimedia.org file
                archival_url=info["url"],
                audio_format=info.get("mime"),
            ))
        if "continue" not in data:
            break
        params.update(data["continue"])  # the API pages results 50 at a time
    return found


def fetch_aporee(search_words: str) -> list[Candidate]:
    """Geotagged radio aporee recordings on archive.org matching some words."""
    params = {
        "q": f'collection:radio-aporee-maps AND ({search_words})',
        "fl[]": ["identifier", "title", "licenseurl", "coverage", "date"],
        "rows": "200", "output": "json",
    }
    url = "https://archive.org/advancedsearch.php"
    docs = requests.get(url, params=params, headers=HEADERS, timeout=30).json()["response"]["docs"]
    found = []
    for doc in docs:
        coverage = str(doc.get("coverage", ""))
        lat = re.search(r"latitude=(-?[\d.]+)", coverage)
        lng = re.search(r"longitude=(-?[\d.]+)", coverage)
        found.append(Candidate(
            source="archive.org",
            title=str(doc.get("title", doc["identifier"])),
            page_url=f"https://archive.org/details/{doc['identifier']}",
            license=license_from_url(str(doc.get("licenseurl", ""))),
            year=int(str(doc["date"])[:4]) if doc.get("date") else None,
            lat=float(lat.group(1)) if lat else None,
            lng=float(lng.group(1)) if lng else None,
        ))
    return found


def license_from_url(url: str) -> str:
    """Turn a Creative Commons URL into a short readable name."""
    if "publicdomain/mark" in url:
        return "Public Domain Mark"
    if "publicdomain/zero" in url:
        return "CC0"
    match = re.search(r"licenses/([a-z-]+)/", url)
    return f"CC {match.group(1).upper()}" if match else "unknown"


def fetch_freesound(query: str, token: str) -> list[Candidate]:
    """Freesound search limited to CC0 and CC BY. Get a key at freesound.org/apiv2/apply."""
    params = {
        "query": query, "token": token, "page_size": "150",
        "filter": 'license:("Creative Commons 0" OR "Attribution")',
        "fields": "id,name,license,username,geotag,url,previews,duration",
    }
    url = "https://freesound.org/apiv2/search/text/"
    results = requests.get(url, params=params, headers=HEADERS, timeout=30).json().get("results", [])
    found = []
    for r in results:
        lat, lng = (float(x) for x in r["geotag"].split()) if r.get("geotag") else (None, None)
        found.append(Candidate(
            source="freesound", title=r["name"], page_url=r["url"],
            license=license_from_url(r["license"]), attribution=r["username"],
            lat=lat, lng=lng,
            audio_url=r.get("previews", {}).get("preview-hq-mp3"),
            audio_format="audio/mpeg",
            duration_seconds=r.get("duration"),
        ))
    return found


# ------------------------------------------------------------------
# STEP 2: turn web pages into real audio files a player can load
# ------------------------------------------------------------------

# Order matters: the first format found wins. MP3 plays in every browser,
# Ogg support is patchy on Apple devices, and FLAC/WAV are too big to stream.
STREAM_PREFERENCE = ["VBR MP3", "MP3", "Ogg Vorbis", "Opus"]
ARCHIVAL_PREFERENCE = ["Flac", "24bit Flac", "WAVE"]


def pick_file(files: list[dict], preference: list[str]) -> Optional[dict]:
    """Return the file whose format ranks highest in the preference list."""
    for wanted in preference:            # outer loop = priority order
        for f in files:
            if f.get("format") == wanted:
                return f
    return None


def parse_length(value: str) -> Optional[float]:
    """archive.org gives lengths as '516.12' or '08:36'. Convert both to seconds."""
    try:
        if ":" in value:
            seconds = 0.0
            for part in value.split(":"):   # '1:02:03' -> ((1*60)+2)*60+3
                seconds = seconds * 60 + float(part)
            return seconds
        return float(value)
    except ValueError:
        return None


def resolve_archive(c: Candidate) -> None:
    identifier = c.page_url.rstrip("/").split("/details/")[-1]
    meta = requests.get(f"https://archive.org/metadata/{identifier}",
                        headers=HEADERS, timeout=30).json()
    files = meta.get("files", [])
    base = f"https://archive.org/download/{identifier}/"
    stream = pick_file(files, STREAM_PREFERENCE)
    original = pick_file(files, ARCHIVAL_PREFERENCE)
    if stream:
        # quote() makes names with spaces or Arabic letters safe inside a URL.
        c.audio_url = base + quote(stream["name"])
        c.audio_format = stream["format"]
        c.duration_seconds = parse_length(str(stream.get("length", "")))
    if original:
        c.archival_url = base + quote(original["name"])


def resolve_commons(c: Candidate) -> None:
    # The page URL is percent-encoded (%C4%9F...), so decode it back to a title.
    title = unquote(c.page_url.split("/wiki/")[-1])
    params = {"action": "query", "format": "json", "titles": title,
              "prop": "imageinfo", "iiprop": "url|mime"}
    data = requests.get("https://commons.wikimedia.org/w/api.php",
                        params=params, headers=HEADERS, timeout=30).json()
    page = next(iter(data["query"]["pages"].values()))
    info = page["imageinfo"][0]
    c.audio_url = c.archival_url = info["url"]
    c.audio_format = info.get("mime")


def resolve_freesound(c: Candidate, token: str) -> None:
    sound_id = re.search(r"/sounds/(\d+)", c.page_url).group(1)
    params = {"token": token, "fields": "previews,duration"}
    data = requests.get(f"https://freesound.org/apiv2/sounds/{sound_id}/",
                        params=params, headers=HEADERS, timeout=30).json()
    c.audio_url = data["previews"]["preview-hq-mp3"]
    c.audio_format = "audio/mpeg"
    c.duration_seconds = data.get("duration")
    c.notes.append("Freesound preview MP3. The original file needs an OAuth2 login to download.")


def check_playable(url: str) -> bool:
    """Ask the server about the file without downloading all of it."""
    try:
        r = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if r.status_code in (403, 405):
            # Some servers refuse HEAD. Request just the first byte instead.
            r = requests.get(url, headers={**HEADERS, "Range": "bytes=0-0"},
                             timeout=20, stream=True)
        content_type = r.headers.get("Content-Type", "")
        return r.status_code in (200, 206) and (
            content_type.startswith("audio/") or "ogg" in content_type)
    except requests.RequestException:
        return False


TEMPLATE = [{
    "file": "EXAMPLE_fes_zawiya_dhikr.mp3",
    "title": "Friday dhikr at a zawiya in Fes",
    "license": "Own recording",
    "year": 2024,
    "lat": 34.0646,
    "lng": -4.9737,
    "attribution": "Recorded by Hamza Khan",
    "source_url": "",
    "notes": "Anything future-you should know about this file"
}]


def load_local() -> list[Candidate]:
    """Read your own audio files and their descriptions from manual_sources.json."""
    LOCAL_DIR.mkdir(exist_ok=True)          # exist_ok=True: no error if it's already there
    if not MANUAL_PATH.exists():
        MANUAL_PATH.write_text(json.dumps(TEMPLATE, indent=2), encoding="utf-8")
        print(f"Created {MANUAL_PATH.name} and {LOCAL_DIR.name}/. Fill them in and run again.")
        return []

    entries = json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
    found, described = [], set()
    for entry in entries:
        name = entry["file"]
        if name.startswith("EXAMPLE"):
            continue                        # skip the template row
        described.add(name)
        audio = LOCAL_DIR / name
        c = Candidate(
            source="local",
            title=entry.get("title", name),
            page_url=entry.get("source_url") or f"local:{name}",
            license=entry.get("license", "unknown"),
            year=entry.get("year"), lat=entry.get("lat"), lng=entry.get("lng"),
            attribution=entry.get("attribution"),
            audio_url=str(audio), archival_url=str(audio),
            audio_format=audio.suffix.lstrip(".").lower(),
            playable=audio.exists(),
        )
        if entry.get("notes"):
            c.notes.append(entry["notes"])
        if not audio.exists():
            c.notes.append(f"File not found in {LOCAL_DIR.name}/")
        elif MutagenFile:
            info = MutagenFile(audio)
            c.duration_seconds = round(info.info.length, 1) if info else None
        found.append(c)

    # Set difference: files sitting in the folder that no JSON entry mentions.
    on_disk = {p.name for p in LOCAL_DIR.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS}
    for name in sorted(on_disk - described):
        print(f"  Not described in {MANUAL_PATH.name} yet: {name}")
    print(f"Loaded {len(found)} local recordings.")
    return found


def resolve_all(candidates: list[Candidate], token: Optional[str]) -> None:
    for c in candidates:
        if c.source == "local":
            continue            # already checked on disk; no web requests needed
        try:
            if not c.audio_url:
                if c.source == "archive.org":
                    resolve_archive(c)
                elif c.source == "commons":
                    resolve_commons(c)
                elif c.source == "freesound" and token:
                    resolve_freesound(c, token)
            c.playable = check_playable(c.audio_url) if c.audio_url else False
            if not c.playable:
                c.notes.append("No playable audio file found yet.")
        except (requests.RequestException, KeyError, AttributeError, StopIteration) as err:
            c.playable = False
            c.notes.append(f"Resolver error: {err}")
        time.sleep(0.5)  # be polite: free archives are not built for rapid-fire requests


def main() -> None:
    # Fail fast: prove we can write the output BEFORE spending minutes on requests.
    try:
        OUTPUT_PATH.touch()
    except OSError as err:
        raise SystemExit(f"Can't write to {OUTPUT_PATH}: {err}")

    candidates = list(VERIFIED_SEED)
    jobs = [
        load_local,             # a function name without () is passed, not called yet
        lambda: fetch_commons_category("Jabbar_Garyagdioglu"),
        lambda: fetch_commons_category("Ottoman_music"),
        lambda: fetch_commons_category("Muezzins"),
        lambda: fetch_aporee('adhan OR azan OR muezzin OR "call to prayer" OR ezan OR zikr OR dhikr'),
    ]
    token = os.environ.get("FREESOUND_TOKEN")
    if token:
        for word in ["adhan", "zikr", "sufi", "qawwali", "muezzin", "ezan"]:
            jobs.append(lambda w=word: fetch_freesound(w, token))
    else:
        print("No FREESOUND_TOKEN set, skipping Freesound.")

    for job in jobs:
        try:
            candidates.extend(job())
        except (requests.RequestException, KeyError, ValueError) as err:
            print(f"One source failed, continuing: {err}")

    # Remove duplicates by page URL, keeping the first (hand-verified) copy.
    unique = {}
    for c in candidates:
        unique.setdefault(c.page_url, c)
    sorted_list = [classify(c) if c.tier == "unsorted" else c for c in unique.values()]

    print(f"Resolving audio files for {len(sorted_list)} candidates (this takes a minute)...")
    resolve_all(sorted_list, token)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump([asdict(c) for c in sorted_list], f, ensure_ascii=False, indent=2)

    for tier in "ABC":
        print(f"Tier {tier}: {sum(c.tier == tier for c in sorted_list)}")
    playable = sum(bool(c.playable) for c in sorted_list)
    print(f"Playable audio files: {playable} of {len(sorted_list)}")
    print(f"Saved {len(sorted_list)} candidates to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

### inspect_results.py

```python
"""
inspect_results.py
Summarises sawt_candidates.json so you can see what the harvester found.
Run it after sawt_harvester.py:  python inspect_results.py
"""

import json
from collections import Counter
from pathlib import Path

# Look for the JSON next to this script, wherever the terminal is.
path = Path(__file__).resolve().parent / "sawt_candidates.json"
if not path.exists():
    raise SystemExit(f"No results yet. Run sawt_harvester.py first (looked for {path}).")

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
reasons = Counter(n.split(":")[0] for c in items if not c["playable"] for n in c["notes"])
for reason, count in reasons.most_common():
    print(f"  {count:>3}  {reason}")

ready = [c for c in items if c["tier"] == "A" and c["playable"]]
print(f"\nReady to use (Tier A and playable): {len(ready)}")
for c in ready:
    print(f"  [{c['source']}] {c['title']}")
```

### freesound_counts.py

```python
"""
freesound_counts.py
Asks Freesound how many CC0 / CC BY sounds match each search word,
so you know which searches are worth harvesting before running the big script.
Needs FREESOUND_TOKEN set.  Run:  python freesound_counts.py
"""

import os

import requests

token = os.environ.get("FREESOUND_TOKEN")
if not token:
    raise SystemExit("Set FREESOUND_TOKEN first (see the setup guide).")

for word in ["adhan", "muezzin", "ezan", "zikr", "sufi", "qawwali"]:
    params = {
        "query": word,
        "token": token,
        "page_size": "1",  # we only want the total count, so ask for one result
        "filter": 'license:("Creative Commons 0" OR "Attribution")',
    }
    data = requests.get("https://freesound.org/apiv2/search/text/", params=params, timeout=30).json()
    # {word:>10} right-aligns the word in 10 characters so the numbers line up.
    print(f"{word:>10}: {data.get('count', data)}")
```

### manual_sources.json (template the harvester creates)

```json
[
  {
    "file": "EXAMPLE_fes_zawiya_dhikr.mp3",
    "title": "Friday dhikr at a zawiya in Fes",
    "license": "Own recording",
    "year": 2024,
    "lat": 34.0646,
    "lng": -4.9737,
    "attribution": "Recorded by Hamza Khan",
    "source_url": "",
    "notes": "Anything future-you should know about this file"
  }
]
```

---

## 11. Next steps (not built yet)

1. **Freesound paging.** Fetch more than 150 results for words whose count is higher (use `freesound_counts.py` first).
2. **Recitation and adhan support.** Add Quran search terms, a `tilawa` / `adhan` genre, and a `stream_only` rights type so licensed-stream content is never downloaded.
3. **Review step.** A quick yes/no pass over Tier B items.
4. **Convert to the app schema.** Turn approved items into `SoundTrack` and `SoundHub` JSON, assigning each recording to its nearest hub.
5. **More classical sources.** Harvard's pre-1923 Arabic 78s and the UCSB discography (1925 and earlier) for maqam, dastgah, and muqam.

## 12. Gallica: the Archives de la Parole

`gallica_harvester.py` opens a source unlike the three we started with.

Freesound, Wikimedia Commons and archive.org are places where the public uploads
recordings. That is why 69 of the first 101 tracks are calls to prayer captured on
phones after 2005: nobody uploads a 1913 Pathé disc to Freesound. The Archives de la
Parole is a state archive of 78rpm discs, catalogued by librarians and digitised by
the Bibliothèque nationale de France, and Gallica reports **2,265 sound records** in
it, each published with `dc:rights = domaine public`.

Its records carry what a scraped web page never does: a catalogue date with an
honesty notation, a shelfmark, a label, matrix numbers, a language code, and a
bracketed classification series such as `[Traditions. Asie. Turquie]`.

### The date notation is the useful part

Gallica writes an uncertain date by replacing the unknown digits with dots.

| catalogue value | meaning | latest possible year | clears the 1925 US cutoff |
|---|---|---|---|
| `1913` | exact | 1913 | yes |
| `191.` | some year in the 1910s | 1919 | yes |
| `192.` | some year in the 1920s | 1929 | no |
| `19..` | 20th century, unknown | 1999 | no |

Judging rights by the latest year a record could have is the same rule
`build_site_data.py` already applies to the Garyagdioğlu discs. A catalogue that
tells you how sure it is beats one that guesses a year and looks confident.

### What the catalogue actually holds

The `--report` on all 2,265 records settled in one pass what guesswork could not.

**723 records are in the languages this project maps.** Of those, **147 clear the US
cutoff and 576 do not**, and the split is not random.

| region | records | clear the cutoff |
|---|---|---|
| Morocco | 368 | 21 |
| India | 209 | 179 |
| Turkey | 102 | 0 |
| Algeria | 99 | 0 |
| Caucasus and Central Asia | 125 | 123 |
| Tunisia | 26 | 0 |

What clears is the 1910s Pathé series recorded across the Russian empire: Tatar, Uzbek,
Tajik, Turkmen, Azerbaijani, with mode names like `Ufari ušak` and `Boâty Širaz` printed
on the labels. What fails is almost the entire 1920s and 1930s North African and Turkish
commercial catalogue, which is the musically richest part of the collection.

That is not a defeat. It is the BnF letter, made specific.

### Run it in this order

```
python gallica_harvester.py --probe          # API and one audio download, changes nothing
python gallica_harvester.py --search         # page the catalogue into gallica_records.json
python gallica_harvester.py --report         # describe what came back
python gallica_harvester.py --filter         # select, and list what needs permission
python gallica_harvester.py --fetch --limit 20   # download, in batches
python make_web_audio.py                     # transcode to Opus
python review.py                             # listen and decide
python build_site_data.py --write
python prepare_web.py
```

`--probe` changes nothing. It exists because the step everything else depends on,
whether Gallica's `.audio` URLs hand a plain HTTP client real bytes, could not be tested
anywhere except your machine. It confirmed `audio/mp3` with an ID3 header, and it also
showed that **Gallica ignores `Range` headers**: a request for the first 2 KB returned
`200` with the whole 2 MB file. An ignored header looks exactly like a working one, so
that fact is now recorded as a named constant rather than rediscovered later.

`--filter` writes two files:

- `gallica_selected.json`, the 147 discs we can harvest today
- `gallica_permission.md`, the 576 we cannot, grouped by series, **with BnF shelfmarks**,
  and separating "provably after the cutoff" from "too vaguely dated to establish"

The second is the more valuable document. A letter that says *339 Moroccan discs,
shelfmarks AP-3120 through AP-3460, already digitised and already public domain in
France* is a different kind of letter from one expressing interest in a collection.

### Placement, and why every Gallica record says `tradition`

Many records state where the disc was cut:

```
Enregistrement : (Algérie) Alger, 00-04-1929
Enregistrement : Paris, Université de Paris, La Sorbonne, 03-03-1914
```

That second one is Begum Fyzee-Rahamin singing Urdu song. In Paris. The Archives de la
Parole brought visiting performers to the Sorbonne as well as buying discs pressed
abroad, so the recording place and the tradition place are genuinely different facts.

Every Gallica record is therefore placed by **tradition**, with the recording location
kept as a note. A map that put Indian song in Paris because that is where the microphone
stood would be accurate and useless. We learned this the expensive way with the Isfahan
gazel, which the gazetteer filed in Iran because a makam shares a name with a city.

### Three bugs the offline tests caught

The network stages cannot be tested from the assistant's sandboxes, so everything that
does not need the network is tested hard, against XML and catalogue records copied
verbatim out of real Gallica responses.

1. **`notes` must be a list.** Every other script treats it as one, and `genres.py` does
   `" ".join(notes)`. Handing it a string would not crash: `join` would iterate the
   characters and turn `catalogue` into `c a t a l o g u e`, destroying every keyword
   match without a word of complaint. `genres.py` now normalises a string to a list too.

2. **A progress line that lied.** `--fetch --limit 3` reported "6 already fetched" on a
   run that had fetched nothing, because it subtracted the trimmed batch from the total
   and called the difference "done".

3. **A test that graded the wrong file.** The fetch test did `sys.path.insert(0, ...)`
   pointing at another copy of the project, which shadowed the local `genres.py`. Every
   classification assertion was silently checking the old module.

`genres.py` also learned the transliterations the BnF catalogued from disc labels:
`usak` for ushshaq, `moual` for mawwal, `nihavend`, `taslib`, `dejra`. Re-running the
classifier over all 571 existing candidates changed **zero** of them, so the new
vocabulary is purely additive.
