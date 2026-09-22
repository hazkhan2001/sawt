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

import argparse
import json
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import date
from typing import Optional

import requests

from config import load_secret, keep_awake

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
# A preview run writes here instead, so a fast look can never clobber real results.
PREVIEW_PATH = SCRIPT_DIR / "sawt_candidates_preview.json"

# Your own files: drop audio in this folder and describe each one in the JSON file.
LOCAL_DIR = SCRIPT_DIR / "sawt_local_audio"
MANUAL_PATH = SCRIPT_DIR / "manual_sources.json"
RETRYABLE_STATUS = (429, 500, 502, 503, 504)   # "come back later", not "this file is dead"

# keep_awake now lives in config.py, shared by every long-running script.
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
# Wikimedia's policy asks automated clients to identify themselves and give a way to
# be contacted. A vague User-Agent is one reason they start refusing requests.
HEADERS = {"User-Agent": "SawtHarvester/0.3 (Sawt heritage sound map; hazkhan2001@gmail.com)"}


def get_json(url: str, params=None, headers=None, attempts: int = 3, timeout: int = 30) -> dict:
    """
    Fetch a URL and parse JSON, with a clear error when the answer is not JSON.

    requests' .json() on an HTML error page raises
        Expecting value: line 1 column 1 (char 0)
    which tells you nothing. Checking the status code first turns that into
    "429 Too Many Requests", which tells you everything.
    """
    for attempt in range(1, attempts + 1):
        response = requests.get(url, params=params, headers=headers or HEADERS, timeout=timeout)

        if response.status_code in RETRYABLE_STATUS and attempt < attempts:
            wait = float(response.headers.get("Retry-After", 0)) or 2.0 * attempt
            print(f"    {response.status_code}, waiting {wait:.0f}s and retrying")
            time.sleep(wait)
            continue

        if response.status_code != 200:
            raise requests.RequestException(
                f"{response.status_code} {response.reason} from {response.url[:80]}")

        try:
            return response.json()
        except ValueError as err:
            snippet = response.text[:120].replace("\n", " ")
            raise requests.RequestException(
                f"expected JSON, got {response.headers.get('Content-Type')}: {snippet}") from err

    raise requests.RequestException(f"gave up after {attempts} attempts: {url}")


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
    category: Optional[str] = None        # "recitation" items are held back, see spec section 8
    found_by: Optional[str] = None        # which search turned this up, useful when reviewing


# ------------------------------------------------------------------
# Search terms, across scripts
# ------------------------------------------------------------------
#
# Freesound titles are whatever the uploader typed, so an English-only word list
# can only find recordings an English speaker labelled. Each search below carries:
#
#   query    what we send to Freesound
#   accept   spellings that must appear in the result's name or tags
#   match    how strictly to compare (see build_pattern below)
#   category "recitation" marks Quran material, held back until spec section 8
#            has its own player rules. Everything else is unmarked.

MATCH_WORD = "word"      # \bX\b   whole word only. For short words that collide: oud, saz
MATCH_PREFIX = "prefix"  # \bX     allows suffixes. Turkish ezan/ezani, Russian azan/azana
MATCH_LOOSE = "loose"    # X       substring. Arabic script glues prefixes on: al- + adhan

FREESOUND_SEARCHES = [
    # --- English and general transliterations ---
    {"query": "adhan", "accept": ["adhan", "adzan", "azan", "azaan", "athan"], "match": MATCH_PREFIX},
    {"query": "call to prayer", "accept": ["call to prayer", "calltoprayer"], "match": MATCH_LOOSE},
    {"query": "muezzin", "accept": ["muezzin", "muazzin", "mu'azzin", "moazzen"], "match": MATCH_PREFIX},
    {"query": "dhikr", "accept": ["dhikr", "zikr", "zikir", "hadra", "hadhra"], "match": MATCH_PREFIX},
    {"query": "sufi", "accept": ["sufi", "sufism", "tasavvuf", "tasawwuf"], "match": MATCH_PREFIX},
    {"query": "qawwali", "accept": ["qawwali", "qawali", "qawwal"], "match": MATCH_PREFIX},
    {"query": "nasheed", "accept": ["nasheed", "nashid", "anasheed", "ilahi", "inshad"], "match": MATCH_PREFIX},
    {"query": "naat", "accept": ["naat", "na't"], "match": MATCH_WORD},
    {"query": "maqam", "accept": ["maqam", "makam", "mugham", "mugam", "muqam"], "match": MATCH_PREFIX},
    {"query": "mevlevi", "accept": ["mevlevi", "mevlana", "semazen", "sema", "whirling"], "match": MATCH_PREFIX},

    # --- Arabic script (Arabic, Persian, Urdu). MATCH_LOOSE because the definite
    #     article al- and the Persian ezafe attach directly to the noun. ---
    {"query": "أذان", "accept": ["اذان", "أذان", "آذان"], "match": MATCH_LOOSE},
    {"query": "مؤذن", "accept": ["مؤذن", "موذن"], "match": MATCH_LOOSE},
    {"query": "ذكر", "accept": ["ذكر", "ذکر"], "match": MATCH_LOOSE},
    {"query": "حضرة", "accept": ["حضره", "حضرة"], "match": MATCH_LOOSE},
    {"query": "صوفي", "accept": ["صوفي", "صوفی", "تصوف"], "match": MATCH_LOOSE},
    {"query": "نشيد", "accept": ["نشيد", "اناشيد", "انشاد"], "match": MATCH_LOOSE},
    {"query": "مولد", "accept": ["مولد", "مولود"], "match": MATCH_LOOSE},
    {"query": "قوالي", "accept": ["قوالي", "قوالی"], "match": MATCH_LOOSE},
    {"query": "مقام", "accept": ["مقام"], "match": MATCH_LOOSE},
    {"query": "دستگاه", "accept": ["دستگاه"], "match": MATCH_LOOSE},
    {"query": "سنتور", "accept": ["سنتور"], "match": MATCH_LOOSE},
    {"query": "کمانچه", "accept": ["كمانچه", "كمانچە"], "match": MATCH_LOOSE},
    {"query": "مداحی", "accept": ["مداحي", "مداح"], "match": MATCH_LOOSE},

    # --- Turkish. MATCH_PREFIX because Turkish glues suffixes on the end:
    #     ezan, ezani, ezanda are all the same word. ---
    {"query": "ezan", "accept": ["ezan"], "match": MATCH_PREFIX},
    {"query": "müezzin", "accept": ["müezzin", "muezzin"], "match": MATCH_PREFIX},
    {"query": "ilahi", "accept": ["ilahi", "ilahisi"], "match": MATCH_PREFIX},
    {"query": "tekbir", "accept": ["tekbir"], "match": MATCH_PREFIX},
    {"query": "kaside", "accept": ["kaside", "qasida", "qasidah", "kasidah"], "match": MATCH_PREFIX},
    {"query": "dergah", "accept": ["dergah", "dergâh", "tekke", "zawiya", "zaviye"], "match": MATCH_PREFIX},
    {"query": "ney", "accept": ["ney", "nay", "neyzen"], "match": MATCH_WORD},
    {"query": "kudüm", "accept": ["kudüm", "kudum", "bendir", "def"], "match": MATCH_WORD},
    {"query": "bağlama", "accept": ["bağlama", "baglama", "saz"], "match": MATCH_PREFIX},
    {"query": "zurna", "accept": ["zurna", "davul"], "match": MATCH_PREFIX},
    {"query": "kanun", "accept": ["kanun", "qanun", "qanoun"], "match": MATCH_WORD},

    # --- Russian. MATCH_PREFIX because Russian nouns take case endings:
    #     azan, azana, azanom. ---
    {"query": "азан", "accept": ["азан"], "match": MATCH_PREFIX},
    {"query": "муэдзин", "accept": ["муэдзин", "муэззин"], "match": MATCH_PREFIX},
    {"query": "зикр", "accept": ["зикр"], "match": MATCH_PREFIX},
    {"query": "суфий", "accept": ["суфи", "суфий", "суфийск"], "match": MATCH_PREFIX},
    {"query": "мечеть", "accept": ["мечет", "мечеть"], "match": MATCH_PREFIX},
    {"query": "мугам", "accept": ["мугам", "мугham"], "match": MATCH_PREFIX},

    # --- Urdu, Indonesian and Malay ---
    {"query": "adzan", "accept": ["adzan", "azan"], "match": MATCH_PREFIX},
    {"query": "sholawat", "accept": ["sholawat", "selawat", "salawat"], "match": MATCH_PREFIX},
    {"query": "qasidah", "accept": ["qasidah", "kasidah", "gambus"], "match": MATCH_PREFIX},
    {"query": "masjid", "accept": ["masjid", "mosque", "mescit", "мечет"], "match": MATCH_PREFIX},

    # --- Azeri, Uzbek and Uyghur. These cover the Shusha/Baku and Kashgar hubs. ---
    {"query": "mugham", "accept": ["mugham", "muğam", "mugam"], "match": MATCH_PREFIX},
    {"query": "muqam", "accept": ["muqam", "mukam"], "match": MATCH_PREFIX},
    {"query": "xanende", "accept": ["xanende", "xanəndə", "khanende", "asiq", "aşıq", "ashiq"], "match": MATCH_PREFIX},
    {"query": "dutar", "accept": ["dutar", "dutor"], "match": MATCH_WORD},
    {"query": "tanbur", "accept": ["tanbur", "tambur", "tanbour"], "match": MATCH_PREFIX},
    {"query": "kamancha", "accept": ["kamancha", "kamancheh", "kamança", "kemence"], "match": MATCH_PREFIX},
    {"query": "balaban", "accept": ["balaban", "duduk"], "match": MATCH_PREFIX},
    {"query": "duduk", "accept": ["duduk"], "match": MATCH_WORD},
    {"query": "oud", "accept": ["oud", "ud", "'ud", "lute"], "match": MATCH_WORD},

    # --- Quran recitation. QUARANTINED: these are found and stored, but marked so
    #     they stay out of the music pool until spec task 4 builds the separate
    #     Recitation and Adhan category with its own playback rules. ---
    {"query": "quran", "accept": ["quran", "qur'an", "koran", "coran"], "match": MATCH_PREFIX,
     "category": "recitation"},
    {"query": "tilawa", "accept": ["tilawa", "tilawah", "tajwid", "tajweed", "mujawwad"], "match": MATCH_PREFIX,
     "category": "recitation"},
    {"query": "قرآن", "accept": ["قرآن", "قران", "تلاوه", "تلاوة", "تجويد"], "match": MATCH_LOOSE,
     "category": "recitation"},
    {"query": "коран", "accept": ["коран"], "match": MATCH_PREFIX, "category": "recitation"},
    {"query": "mengaji", "accept": ["mengaji", "ngaji"], "match": MATCH_PREFIX, "category": "recitation"},
]


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
    # ND (NoDerivatives) slipped through before, because "CC BY-ND" contains "cc by".
    # \b is a word boundary, and "-" counts as one, so this matches "by-nd" but not "and".
    elif re.search(r"\bnd\b", lic) or "noderiv" in lic.replace(" ", "").replace("-", ""):
        c.tier = "B"
        c.notes.append("NoDerivatives: playing the file whole may be fine, "
                       "but trimming, excerpting or remixing it is not. Decide by hand.")
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


COMMONS_API = "https://commons.wikimedia.org/w/api.php"


# Commons hosts Wiktionary and Lingua Libre pronunciation clips: one person saying
# one word into a laptop mic, to illustrate a dictionary entry. They match every
# search term perfectly and are useless here. Their filenames follow fixed patterns.
# Wikimedia language codes used as filename prefixes. Listing them explicitly matters:
# an earlier version matched any two letters plus a hyphen, which swallowed the real
# places "At-Tuweisa, Jordan" and "El-Hussein Mosque". Arabic al-/el- names look
# exactly like a language prefix, so the rule has to know which codes are real.
WIKI_LANGS = ("en|de|fr|es|nl|pl|ru|it|pt|sw|ca|ast|az|tr|uk|bg|ro|sv|da|fi|cs")
AUDIO_SUFFIX = r"(ogg|oga|wav|mp3|flac)"

PRONUNCIATION_PATTERNS = re.compile(
    rf"^ll-q\d+\b"                                      # LL-Q150 (fra)-Vealhurl-adhan.wav
    rf"|^({WIKI_LANGS})-[a-z]{{2}}-"                      # En-us-mosque.ogg, Sw-ke-sufi.flac
    rf"|^({WIKI_LANGS})-[a-z]+--"                         # Fr-Paris--qasida.ogg
    rf"|^({WIKI_LANGS})-[a-z-]+\d*\.{AUDIO_SUFFIX}$"      # De-Muezzin.ogg, Nl-oud-ministers.ogg
    rf"|pronunciation",
    re.IGNORECASE)


def is_pronunciation_clip(title: str) -> bool:
    """True for dictionary pronunciation recordings, which are not soundscapes."""
    return bool(PRONUNCIATION_PATTERNS.search(title))


def commons_page_to_candidate(page: dict, search: Optional[dict] = None) -> Optional[Candidate]:
    """One Commons API page into a Candidate, or None if it is not audio."""
    search = search or {}
    info = page["imageinfo"][0]
    if info.get("mediatype") != "AUDIO":
        return None                       # categories and searches also return images
    if is_pronunciation_clip(page["title"].removeprefix("File:")):
        return None                       # dictionary clips, not recordings of a place
    meta = info.get("extmetadata", {})
    year_text = meta.get("DateTimeOriginal", {}).get("value", "")
    year_match = re.search(r"(18|19|20)\d{2}", year_text)
    # coordinates is a list because a page can mark several places. Take the first.
    coords = (page.get("coordinates") or [{}])[0]
    return Candidate(
        source="commons",
        title=page["title"].removeprefix("File:"),
        page_url=info["descriptionurl"],
        license=meta.get("LicenseShortName", {}).get("value", "unknown"),
        year=int(year_match.group()) if year_match else None,
        lat=coords.get("lat"),
        lng=coords.get("lon"),
        audio_url=info["url"],            # direct upload.wikimedia.org file
        archival_url=info["url"],
        audio_format=info.get("mime"),
        category=search.get("category"),
        found_by=search.get("query"),
    )


def fetch_commons_category(category: str) -> list[Candidate]:
    """Every audio file in a Commons category, with license and date."""
    params = {
        "action": "query", "format": "json",
        "generator": "categorymembers", "gcmtitle": f"Category:{category}",
        "gcmtype": "file", "gcmlimit": "50",
        # coordinates comes from the {{Location}} template on the file page. Without it
        # a Commons recording has no place on the globe, which is the whole point.
        "prop": "imageinfo|coordinates", "coprop": "type|name", "colimit": "max",
        "iiprop": "url|mediatype|mime|extmetadata",
    }
    found = []
    while True:
        data = get_json(COMMONS_API, params=params)
        for page in data.get("query", {}).get("pages", {}).values():
            c = commons_page_to_candidate(page)
            if c:
                found.append(c)            # a category is curated, so no relevance filter
        if "continue" not in data:
            break
        params.update(data["continue"])    # the API pages results 50 at a time
    return found


def fetch_commons_search(search: dict) -> list[Candidate]:
    """
    Commons audio files matching a term, in any script.

    This is where the multilingual terms earn their keep. Commons is catalogued by
    volunteers worldwide, so its file titles and descriptions are genuinely in Arabic,
    Turkish, Azeri and Russian, unlike Freesound where almost everything is titled in
    English. "filetype:audio" is a CirrusSearch keyword that keeps images out.
    """
    params = {
        "action": "query", "format": "json",
        "generator": "search",
        "gsrsearch": f'{search["query"]} filetype:audio',
        "gsrnamespace": "6",               # namespace 6 is File:
        "gsrlimit": "50",
        # coordinates comes from the {{Location}} template on the file page. Without it
        # a Commons recording has no place on the globe, which is the whole point.
        "prop": "imageinfo|coordinates", "coprop": "type|name", "colimit": "max",
        "iiprop": "url|mediatype|mime|extmetadata",
    }
    data = get_json(COMMONS_API, params=params)
    found, dropped = [], 0
    for page in data.get("query", {}).get("pages", {}).values():
        c = commons_page_to_candidate(page, search)
        if not c:
            continue
        # Commons search matches description text too, so filter on the title the
        # same way we filter Freesound. Same tool, different haystack.
        if looks_relevant({"name": c.title, "tags": []}, search):
            found.append(c)
        else:
            dropped += 1
    if found or dropped:
        print(f"  commons '{search['query']}': kept {len(found)}, dropped {dropped}")
    return found


def fetch_aporee(search_words: str) -> list[Candidate]:
    """Geotagged radio aporee recordings on archive.org matching some words."""
    params = {
        "q": f'collection:radio-aporee-maps AND ({search_words})',
        "fl[]": ["identifier", "title", "licenseurl", "coverage", "date"],
        "rows": "200", "output": "json",
    }
    url = "https://archive.org/advancedsearch.php"
    docs = get_json(url, params=params)["response"]["docs"]
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


FREESOUND_URL = "https://freesound.org/apiv2/search/text/"
FREESOUND_PAGE_SIZE = 150        # the API's maximum
FREESOUND_MAX_PAGES = 8          # a safety belt so one word can't run forever
FREESOUND_FILTER = 'license:("Creative Commons 0" OR "Attribution")'
FREESOUND_FIELDS = "id,name,tags,license,username,geotag,url,previews,duration"


def freesound_headers(token: str) -> dict:
    """
    Auth for Freesound, sent as a header rather than a ?token= parameter.

    This matters for paging. The "next" URL the API hands back repeats the query
    and the filter but NOT the token, so a token passed as a parameter is lost on
    page 2 and the request comes back 401. A header is attached to every request
    we make, so it survives following "next".
    """
    return {**HEADERS, "Authorization": f"Token {token}"}


# Arabic harakat (the small vowel marks) and tatweel (the stretching dash). These are
# optional in writing, so "أَذَان" and "أذان" are the same word with different keystrokes.
ARABIC_MARKS = re.compile(r"[\u064B-\u0652\u0670\u0640]")

# Characters that different keyboards write differently for the same sound. Persian and
# Urdu keyboards produce ک and ی where Arabic keyboards produce ك and ي, and the alef
# carries an optional hamza. Unifying them means one spelling in the list matches all.
SCRIPT_UNIFY = {
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ی": "ي", "ى": "ي",
    "ک": "ك",
    "ۀ": "ه", "ة": "ه",
    "\u200c": " ",      # Persian zero-width non-joiner, invisible but it breaks matching
}


# Uploaders separate words with whatever key is handy. "Call_To_Prayer_Loud_Fes" and
# "call to prayer, loud, Fes" are the same title as far as searching is concerned,
# but "_" counts as a word character in regex, so \b never fires next to it.
SEPARATORS = re.compile(r"[_\-.+/\\()\[\]{}:;,!?'\"]+")


def normalize_text(text: str) -> str:
    """Flatten spelling differences so comparisons are about words, not keyboards."""
    text = text.lower()
    text = ARABIC_MARKS.sub("", text)
    for source, target in SCRIPT_UNIFY.items():
        text = text.replace(source, target)
    text = SEPARATORS.sub(" ", text)
    # Collapse runs of whitespace so a two-word phrase matches however it was spaced.
    return " ".join(text.split())


def build_pattern(term: str, mode: str) -> str:
    """
    Turn an accepted spelling into a regex, at one of three strictness levels.

    The right level depends on how the language builds words:
      MATCH_WORD   \bX\b  "oud" must stand alone, or Dutch "Oude" floods the results
      MATCH_PREFIX \bX    Turkish and Russian add endings: ezan -> ezani, азан -> азана
      MATCH_LOOSE  X      Arabic script attaches al- to the front: أذان -> الأذان

    Using MATCH_WORD everywhere would silently discard most non-English hits.
    """
    escaped = re.escape(normalize_text(term))
    if mode == MATCH_WORD:
        return rf"\b{escaped}\b"
    if mode == MATCH_PREFIX:
        return rf"\b{escaped}"
    return escaped


def looks_relevant(r: dict, search: dict) -> bool:
    """Does any accepted spelling actually appear in this sound's name or tags?"""
    haystack = normalize_text(r.get("name", "") + " " + " ".join(r.get("tags", [])))
    mode = search.get("match", MATCH_WORD)
    return any(re.search(build_pattern(term, mode), haystack)
               for term in search["accept"])


def freesound_to_candidate(r: dict, search: Optional[dict] = None) -> Candidate:
    """Turn one Freesound search result into a Candidate. Split out so paging stays readable."""
    search = search or {}
    # geotag looks like "41.008 28.978". Splitting gives two strings we turn into floats.
    if r.get("geotag"):
        lat, lng = (float(x) for x in r["geotag"].split())
    else:
        lat, lng = None, None
    return Candidate(
        source="freesound", title=r["name"], page_url=r["url"],
        license=license_from_url(r["license"]), attribution=r["username"],
        lat=lat, lng=lng,
        audio_url=r.get("previews", {}).get("preview-hq-mp3"),
        audio_format="audio/mpeg",
        duration_seconds=r.get("duration"),
        category=search.get("category"),
        found_by=search.get("query"),
    )


def fetch_freesound(search: dict, token: str,
                    max_pages: int = FREESOUND_MAX_PAGES) -> list[Candidate]:
    """
    Freesound search limited to CC0 and CC BY, following the API's paging.

    The API answers with {"count": 812, "next": "<url>", "results": [...]}.
    "next" is a complete URL that already carries every parameter, including the
    token, so after the first request we send that URL with no params of our own.
    We stop when "next" is null (the last page) or when max_pages is reached.
    """
    url = FREESOUND_URL
    query = search["query"]
    # Freesound returns 0 hits for an unquoted multi-word query: "call to prayer" finds
    # nothing, while '"call to prayer"' finds 133. Quoting turns it into a phrase search.
    # looks_relevant works from search["accept"], so it never sees the quote marks.
    search_term = f'"{query}"' if " " in query else query
    params = {
        "query": search_term, "page_size": str(FREESOUND_PAGE_SIZE),
        "filter": FREESOUND_FILTER,
        "fields": FREESOUND_FIELDS,
    }
    headers = freesound_headers(token)

    found = []
    dropped = 0
    for page_number in range(1, max_pages + 1):
        data = get_json(url, params=params, headers=headers)

        if "detail" in data and "results" not in data:
            # Freesound reports auth and quota problems in a "detail" field.
            print(f"  Freesound refused '{query}': {data['detail']}")
            break

        results = data.get("results", [])
        for r in results:
            if looks_relevant(r, search):
                found.append(freesound_to_candidate(r, search))
            else:
                dropped += 1

        next_url = data.get("next")
        if not next_url:
            break                  # null "next" means that was the final page

        if page_number == max_pages:
            print(f"  '{query}': stopped at {max_pages} pages of "
                  f"{data.get('count', '?')} total hits. Raise FREESOUND_MAX_PAGES to go deeper.")
            break

        url = next_url             # the next page URL already holds the query and filter
        params = None              # so sending our params again would duplicate them
        time.sleep(0.5)            # be polite between pages

    if dropped:
        print(f"  '{query}': kept {len(found)}, dropped {dropped} as unrelated word-stem matches")
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
    meta = get_json(f"https://archive.org/metadata/{identifier}")
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
    data = get_json(COMMONS_API, params=params)
    page = next(iter(data["query"]["pages"].values()))
    info = page["imageinfo"][0]
    c.audio_url = c.archival_url = info["url"]
    c.audio_format = info.get("mime")


def resolve_freesound(c: Candidate, token: str) -> None:
    sound_id = re.search(r"/sounds/(\d+)", c.page_url).group(1)
    params = {"fields": "previews,duration"}
    data = get_json(f"https://freesound.org/apiv2/sounds/{sound_id}/",
                    params=params, headers=freesound_headers(token))
    if "previews" not in data:
        # A bad or missing token lands here. Without this check the next line would
        # raise KeyError('previews'), which says nothing about the real cause.
        c.notes.append(f"Freesound returned no previews: {data.get('detail', data)}")
        return
    c.audio_url = data["previews"]["preview-hq-mp3"]
    c.audio_format = "audio/mpeg"
    c.duration_seconds = data.get("duration")
    c.notes.append("Freesound preview MP3. The original file needs an OAuth2 login to download.")


def check_playable(url: str, attempts: int = 3) -> tuple[bool, str]:
    """
    Ask the server about the file without downloading all of it.

    Returns (is_playable, reason). The reason is what turns a useless "False" into
    something you can act on: 404 means the link is wrong, 429 means we were simply
    asking too fast.

    429 (Too Many Requests) is retried with a widening wait. Wikimedia sends it
    freely when a script fires HEAD requests in a tight loop, and treating it as a
    dead file marks perfectly good recordings unplayable.
    """
    for attempt in range(1, attempts + 1):
        try:
            r = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
            if r.status_code in (403, 405):
                # Some servers refuse HEAD. Request just the first byte instead.
                r = requests.get(url, headers={**HEADERS, "Range": "bytes=0-0"},
                                 timeout=20, stream=True)
                r.close()

            if r.status_code in RETRYABLE_STATUS and attempt < attempts:
                # Retry-After, when the server sends it, is the polite answer to "how long?"
                wait = float(r.headers.get("Retry-After", 0)) or 2.0 * attempt
                time.sleep(wait)
                continue

            content_type = r.headers.get("Content-Type", "")
            ok = r.status_code in (200, 206) and (
                content_type.startswith("audio/") or "ogg" in content_type)
            return ok, f"{r.status_code} {content_type or 'no content-type'}"

        except requests.RequestException as err:
            if attempt < attempts:
                time.sleep(2.0 * attempt)
                continue
            return False, type(err).__name__

    return False, f"still failing after {attempts} attempts"


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


def save(candidates: list[Candidate], path: Path) -> None:
    """Write results to disk. Called at the end and at every checkpoint."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(c) for c in candidates], f, ensure_ascii=False, indent=2)


def resolve_all(candidates: list[Candidate], token: Optional[str],
                checkpoint_path: Optional[Path] = None,
                checkpoint_list: Optional[list[Candidate]] = None,
                every: int = 25) -> None:
    """
    Resolve and check every candidate, saving partial results as it goes.

    A half-hour job that only writes at the end loses everything if it dies at
    minute 29. Writing every `every` items means a crash costs you the last few
    seconds of work, not the whole run.

    `candidates` is the subset still needing work. `checkpoint_list` is everything
    that belongs in the file. On a --resume run those differ, and saving the subset
    would quietly delete every result the resume just recovered.
    """
    to_save = checkpoint_list if checkpoint_list is not None else candidates
    started = time.monotonic()
    total = len(candidates)
    for index, c in enumerate(candidates, start=1):
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
            if c.audio_url:
                c.playable, reason = check_playable(c.audio_url)
            else:
                c.playable, reason = False, "no audio URL resolved"
            if not c.playable:
                c.notes.append(f"Not playable: {reason}")
        except (requests.RequestException, KeyError, AttributeError, StopIteration) as err:
            c.playable = False
            c.notes.append(f"Resolver error: {err}")
        # Be polite. Wikimedia rate-limits harder than the others, so it waits longer.
        time.sleep(1.5 if c.source == "commons" else 0.5)

        if index % every == 0 or index == total:
            elapsed = time.monotonic() - started
            remaining = elapsed / index * (total - index)      # simple linear estimate
            print(f"  {index}/{total} resolved, about {remaining / 60:.0f} min left",
                  flush=True)                                   # flush: show it now, not at exit
            if checkpoint_path:
                save(to_save, checkpoint_path)


def parse_args() -> argparse.Namespace:
    """
    Read the command line.

    argparse is the standard library's answer to "let the user change one thing
    without editing the script". It builds --help for free from these descriptions.
    action="store_true" means the flag takes no value: present is True, absent is False.
    """
    parser = argparse.ArgumentParser(description="Harvest openly licensed audio for Sawt.")
    parser.add_argument(
        "--preview", action="store_true",
        help="run the searches but skip resolving and checking audio files. "
             "Seconds instead of twenty minutes, and it writes to a separate file.")
    parser.add_argument(
        "--resume", action="store_true",
        help="reuse results already in sawt_candidates.json instead of re-checking them")
    parser.add_argument(
        "--max-pages", type=int, default=FREESOUND_MAX_PAGES,
        help=f"how many Freesound pages to follow per search (default {FREESOUND_MAX_PAGES})")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = PREVIEW_PATH if args.preview else OUTPUT_PATH
    keep_awake("the harvest")

    # Fail fast: prove we can write the output BEFORE spending minutes on requests.
    try:
        output_path.touch()
    except OSError as err:
        raise SystemExit(f"Can't write to {output_path}: {err}")

    candidates = list(VERIFIED_SEED)
    jobs = [
        load_local,             # a function name without () is passed, not called yet
        lambda: fetch_commons_category("Jabbar_Garyagdioglu"),
        lambda: fetch_commons_category("Ottoman_music"),
        lambda: fetch_commons_category("Muezzins"),
        lambda: fetch_aporee(
            'adhan OR azan OR adzan OR muezzin OR "call to prayer" OR ezan OR muezzin '
            'OR zikr OR dhikr OR sufi OR mugham OR muqam OR qawwali OR mosque OR masjid '
            'OR "أذان" OR "مؤذن" OR азан OR муэдзин'),
    ]
    # The same term list, pointed at Commons. Costs one request each and needs no key.
    for search in FREESOUND_SEARCHES:
        jobs.append(lambda s=search: fetch_commons_search(s))

    token = load_secret("FREESOUND_TOKEN")
    if token:
        for search in FREESOUND_SEARCHES:
            # s=search binds the value now. Without it, every lambda would share the
            # loop variable and all 58 jobs would run the last search.
            jobs.append(lambda s=search: fetch_freesound(s, token, max_pages=args.max_pages))
    else:
        print("No FREESOUND_TOKEN set, skipping Freesound.")

    for job in jobs:
        try:
            candidates.extend(job())
        except (requests.RequestException, KeyError, ValueError) as err:
            print(f"One source failed, continuing: {err}")
        time.sleep(0.5)   # 58 searches arriving at once is what got us rate-limited

    # Remove duplicates by page URL, keeping the first (hand-verified) copy.
    unique = {}
    for c in candidates:
        unique.setdefault(c.page_url, c)
    sorted_list = [classify(c) if c.tier == "unsorted" else c for c in unique.values()]

    # Quarantine: recitation is not music. Spec section 8 gives it its own category,
    # its own player rules, and a requirement to show surah and ayah alongside it.
    # Until task 4 builds that, these are collected but flagged so they cannot be
    # mistaken for the music pool.
    for c in sorted_list:
        if c.category == "recitation":
            c.notes.append("QUARANTINED recitation: not for the music pool (spec section 8).")

    if args.preview:
        print(f"Preview: {len(sorted_list)} candidates found. "
              f"Skipping audio resolution (drop --preview for the real run).")
    else:
        if args.resume and output_path.exists():
            # Build a lookup from the previous run, keyed by page URL, and copy over
            # anything already resolved so we do not pay for those requests twice.
            previous = {item["page_url"]: item
                        for item in json.loads(output_path.read_text(encoding="utf-8"))}
            reused = 0
            for c in sorted_list:
                old_item = previous.get(c.page_url)
                if old_item and old_item.get("playable") is not None:
                    for attribute in ("audio_url", "audio_format", "archival_url",
                                      "duration_seconds", "playable"):
                        setattr(c, attribute, old_item.get(attribute))
                    c.notes = old_item.get("notes", c.notes)
                    reused += 1
            print(f"Resuming: reusing {reused} already-resolved candidates.")

        pending = [c for c in sorted_list if c.playable is None]
        # Roughly a second per candidate, more for Commons, which is rate-limited.
        print(f"Resolving audio files for {len(pending)} candidates "
              f"(about {len(pending) // 50} to {len(pending) // 20} minutes)...", flush=True)
        resolve_all(pending, token, checkpoint_path=output_path,
                    checkpoint_list=sorted_list, every=25)

    save(sorted_list, output_path)

    for tier in "ABC":
        print(f"Tier {tier}: {sum(c.tier == tier for c in sorted_list)}")
    recitation = sum(c.category == "recitation" for c in sorted_list)
    if recitation:
        print(f"Quarantined recitation items: {recitation} (excluded from the music pool)")
    if not args.preview:
        playable = sum(bool(c.playable) for c in sorted_list)
        print(f"Playable audio files: {playable} of {len(sorted_list)}")
    print(f"Saved {len(sorted_list)} candidates to {output_path}")


if __name__ == "__main__":
    main()
