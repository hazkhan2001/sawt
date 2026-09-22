"""
gallica_harvester.py
Harvest the BnF's Archives de la Parole from Gallica.

WHY THIS SOURCE
---------------
Everything we have so far came from places where members of the public upload
recordings: Freesound, Wikimedia Commons, archive.org. That is why 69 of our 101
tracks are calls to prayer recorded on phones after 2005. Nobody uploads a 1913
Pathe disc to Freesound.

The Archives de la Parole is the opposite kind of source. It is a state archive of
78rpm discs, catalogued by librarians, digitised by the Bibliotheque nationale de
France, and published on Gallica with dc:rights = "domaine public". Its records
carry real dates, real shelfmarks, matrix numbers, labels, and language codes. The
one record we already have from it, a Pathe disc of Husseyni Saz Semayissi, reached
us by the long way round: someone uploaded it to Commons, and we harvested Commons.

A search of Gallica's SRU endpoint says the collection holds 2,265 sound records.

WHAT THIS SCRIPT DOES NOT DO YET, ON PURPOSE
--------------------------------------------
It does not filter, geocode, or download in bulk. That is deliberate.

The Archives de la Parole was founded in 1911 by Ferdinand Brunot as a LINGUISTIC
survey: its first job was recording French regional dialects, and the foreign music
is a later accretion from donated commercial discs. So "2,265 sound records" is
almost certainly not 2,265 pieces of music, and writing filters now would mean
writing them against what I assume is in there.

We made that mistake before. The Freesound paging bug passed its test because the
test was a mock I wrote, and the mock encoded my beliefs rather than the API's
behaviour. So the order here is: probe, then fetch the whole catalogue as data,
then LOOK at it, and only then decide what to keep.

    python gallica_harvester.py --probe     one search, one record, one audio file
    python gallica_harvester.py --search    page the whole catalogue to disk
    python gallica_harvester.py --report    describe what we actually got

Needs: pip install requests
"""

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from collections import Counter
from pathlib import Path

import requests

from config import keep_awake

SCRIPT_DIR = Path(__file__).resolve().parent
RECORDS = SCRIPT_DIR / "gallica_records.json"
SELECTED = SCRIPT_DIR / "gallica_selected.json"
PERMISSION = SCRIPT_DIR / "gallica_permission.md"

# Same rule as build_site_data.py: a foreign sound recording published 1923-1946 holds
# US copyright for 100 years, so today's cutoff is this year minus 101.
CUTOFF_YEAR = date.today().year - 101

SRU = "https://gallica.bnf.fr/SRU"
OAI_RECORD = "https://gallica.bnf.fr/services/OAIRecord"

# The collection query. Both halves matter:
#   gallica all "Archives de la Parole"  the collection, matched in the record text
#   dc.type all "sonore"                 audio only
# Drop the second half and you get 35,000 hits, because "gallica all" is a full-text
# index across every digitised book in the library and plenty of them mention Asia.
# That near-miss is worth remembering: a query that returns MORE is not a better query.
COLLECTION_QUERY = '(gallica all "Archives de la Parole") and dc.type all "sonore"'

# Gallica caps a page at 50. Asking for more does not error, it silently gives 50,
# which would make a resume loop skip records forever.
PAGE_SIZE = 50
PAUSE_SECONDS = 1.0

# Confirmed by --probe on 2026-09-18: Gallica serves audio/mp3 and IGNORES a Range
# header, answering 200 with the whole file rather than 206 with a slice. So there is
# no cheap way to inspect a file before committing to it, and the download stage must
# budget for full transfers. The first disc probed was ~2 MB for 3 minutes of audio.
GALLICA_HONOURS_RANGE = False

HEADERS = {
    "User-Agent": "Sawt/0.1 (non-commercial cultural mapping project; contact via project page)",
    "Accept": "application/xml",
}

# ElementTree wants namespace URIs written out in full in every tag lookup, which is
# unreadable. The usual fix is a dict passed as the second argument to find/findall,
# letting you write "srw:records" instead of "{http://www.loc.gov/zing/srw/}records".
NS = {
    "srw": "http://www.loc.gov/zing/srw/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

RETRYABLE = {429, 500, 502, 503, 504}


def get_xml(url: str, params: dict | None = None, attempts: int = 4) -> ET.Element:
    """
    Fetch a URL and parse it as XML, checking the status BEFORE parsing.

    The order matters and it is the reason this wrapper exists. requests will happily
    hand you a 503 HTML error page, and ET.fromstring will then raise a ParseError
    about a stray "<" on line 1. You spend twenty minutes debugging your XML parser
    when the actual problem is that the server said no.
    """
    for attempt in range(1, attempts + 1):
        response = requests.get(url, params=params, headers=HEADERS, timeout=(10, 40))
        if response.status_code in RETRYABLE and attempt < attempts:
            wait = float(response.headers.get("Retry-After", 0)) or 2.0 * attempt
            print(f"    {response.status_code}, waiting {wait:.0f}s")
            time.sleep(wait)
            continue
        if response.status_code != 200:
            raise requests.RequestException(
                f"{response.status_code} {response.reason} from {response.url[:100]}")
        try:
            return ET.fromstring(response.content)
        except ET.ParseError as err:
            snippet = response.text[:160].replace("\n", " ")
            raise requests.RequestException(
                f"expected XML, got {response.headers.get('Content-Type')}: {snippet}") from err
    raise requests.RequestException(f"gave up after {attempts} attempts: {url}")


def dc_fields(record: ET.Element) -> dict:
    """
    Flatten one Dublin Core record into a dict of lists.

    Every dc element repeats: a disc has two dc:format lines, three dc:identifier
    lines, two dc:rights. Storing the first and discarding the rest is how you lose
    the matrix number, and the matrix number is how a disc is dated. So every field
    is a list, always, even when it holds one item. Uniform shapes beat convenient ones.
    """
    out: dict[str, list[str]] = {}
    dc = record.find(".//oai_dc:dc", NS)
    if dc is None:
        return out
    for child in dc:
        tag = child.tag.split("}")[-1]
        text = (child.text or "").strip()
        if text:
            out.setdefault(tag, []).append(text)
    return out


def ark_of(fields: dict) -> str | None:
    for ident in fields.get("identifier", []):
        match = re.search(r"(ark:/12148/[A-Za-z0-9]+)", ident)
        if match:
            return match.group(1)
    return None


def search_page(start: int) -> tuple[int, list[dict]]:
    """Return (total, records) for one page. startRecord is 1-based, not 0-based."""
    root = get_xml(SRU, {
        "operation": "searchRetrieve",
        "version": "1.2",
        "query": COLLECTION_QUERY,
        "startRecord": start,
        "maximumRecords": PAGE_SIZE,
    })
    total_node = root.find("srw:numberOfRecords", NS)
    total = int(total_node.text) if total_node is not None else 0
    records = []
    for node in root.findall(".//srw:record", NS):
        fields = dc_fields(node)
        if fields:
            fields["_ark"] = [ark_of(fields) or ""]
            records.append(fields)
    return total, records


def probe() -> None:
    """
    Prove the three things the rest of the script assumes, and change nothing.

    1. the search endpoint answers and reports a total
    2. a record carries the metadata we intend to use
    3. the audio behind a record can actually be downloaded by a plain HTTP client

    Point 3 is the one that decides whether this whole source is viable, and it is
    the one I cannot test from anywhere but your machine: the sandboxes this
    assistant runs in are blocked from gallica.bnf.fr. So it is the first thing the
    script checks, before anything expensive.
    """
    print("1. SEARCH")
    total, records = search_page(1)
    print(f"   {total} sound records in the collection")
    if not records:
        sys.exit("   no records came back; stop here and read the query")

    print("\n2. FIRST RECORD")
    first = records[0]
    for key in ("title", "date", "creator", "language", "description",
                "subject", "rights", "source", "format", "identifier"):
        for value in first.get(key, []):
            print(f"   {key:12} {value[:110]}")

    ark = first["_ark"][0]
    print(f"\n3. AUDIO BEHIND {ark}")
    time.sleep(PAUSE_SECONDS)
    root = get_xml(OAI_RECORD, {"ark": ark.split("/")[-1]})
    files = [node.text for node in root.findall(".//sounds//file") if node.text]
    print(f"   {len(files)} audio file(s) listed by the record service")
    for url in files:
        print(f"     {url}")
    if not files:
        print("   no audio URLs listed. Without these there is nothing to harvest.")
        return

    # GALLICA IGNORES RANGE REQUESTS.
    #
    # The first version of this probe sent "Range: bytes=0-2047" expecting 2 KB and a
    # 206 Partial Content. Gallica answered 200 with no Content-Range and the entire
    # two megabyte file. The header was not refused, it was ignored, which is worse:
    # a refusal is visible, and an ignored header looks like it worked.
    #
    # stream=True stops requests from reading the body into memory on the call. The
    # connection stays open and nothing is transferred until you ask for content, so
    # iter_content with a chunk size lets us take the first slice and then close the
    # connection, which is as close to a cheap look as this server allows. The
    # try/finally matters: close() has to run even if the read raises, or the socket
    # leaks.
    print("\n4. CAN WE ACTUALLY DOWNLOAD IT")
    time.sleep(PAUSE_SECONDS)
    response = requests.get(files[0], headers={**HEADERS, "Accept": "*/*"},
                            stream=True, timeout=(10, 40))
    try:
        first = next(response.iter_content(chunk_size=2048), b"")
        print(f"   status        {response.status_code} {response.reason}")
        print(f"   content-type  {response.headers.get('Content-Type')}")
        print(f"   full size     {response.headers.get('Content-Length')} bytes")
        print(f"   first 16      {first[:16]!r}")
    finally:
        response.close()

    # ID3 is the metadata block an MP3 usually opens with; "fff" at the start is a
    # bare MPEG frame. Either means we were sent audio and not an HTML error page
    # wearing an audio content-type, which is a thing servers do.
    looks_like_audio = first[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    if response.status_code == 200 and looks_like_audio:
        print("\n   Audio is reachable. The source is viable.")
    else:
        print("\n   Audio did NOT come back as audio. Everything downstream depends")
        print("   on this; do not build filters until it is understood.")


def search() -> None:
    """
    Page the whole catalogue to disk, checkpointing after every page.

    Resume works by counting what is already on disk, which is only safe because SRU
    paging over a fixed query is stable. The guard below re-reads the reported total
    on every page: if the collection changed under us mid-run, the count moves and we
    would rather know than silently interleave two different result sets.
    """
    existing = json.loads(RECORDS.read_text(encoding="utf-8")) if RECORDS.exists() else []
    start = len(existing) + 1
    if existing:
        print(f"resuming: {len(existing)} records already on disk")

    total = None
    while True:
        print(f"  records {start}-{start + PAGE_SIZE - 1} ...", end=" ", flush=True)
        page_total, records = search_page(start)
        if total is None:
            total = page_total
            print(f"(of {total})", end=" ")
        elif page_total != total:
            print(f"\n  total changed {total} -> {page_total}; stopping to be safe")
            break
        if not records:
            print("empty page, done")
            break
        existing.extend(records)
        RECORDS.write_text(json.dumps(existing, ensure_ascii=False, indent=1),
                           encoding="utf-8")
        print(f"{len(records)} kept, {len(existing)} total")
        start += len(records)
        if len(existing) >= total:
            break
        time.sleep(PAUSE_SECONDS)

    print(f"\nwrote {len(existing)} records to {RECORDS.name}")


def decade_of(dates: list[str]) -> str:
    """
    Gallica writes an uncertain date by replacing the unknown digits with dots:
    "1913" is exact, "191." is somewhere in the 1910s, "19.." is the 20th century.
    That notation is a gift. It means the catalogue tells you how sure it is, and we
    can judge rights by the LATEST year a record could have, which is the same rule
    build_site_data.py already applies to the Garyagdioglu discs.
    """
    for raw in dates:
        text = raw.strip()
        if re.fullmatch(r"\d{4}", text):
            return text[:3] + "0s (exact year known)"
        if re.fullmatch(r"\d{3}\.", text):
            return text[:3] + "0s"
        if re.fullmatch(r"\d{2}\.\.", text):
            return text[:2] + "00s (century only)"
    return "no date"


def report() -> None:
    """Describe the catalogue we fetched, before deciding what to do with it."""
    if not RECORDS.exists():
        sys.exit("no gallica_records.json yet; run --search first")
    records = json.loads(RECORDS.read_text(encoding="utf-8"))
    print(f"{len(records)} records\n")

    def tally(name: str, values, limit=25):
        counts = Counter(values)
        print(f"-- {name} ({len(counts)} distinct) --")
        for value, n in counts.most_common(limit):
            print(f"  {n:5}  {value[:88]}")
        rest = len(counts) - limit
        if rest > 0:
            print(f"        ... and {rest} more")
        print()

    tally("language", (lang for r in records for lang in r.get("language", ["(none)"])))
    tally("decade", (decade_of(r.get("date", [])) for r in records))

    # The description field is where the librarians wrote the classification, in the
    # shape "[Traditions. Asie. Turquie]". That bracketed series is the single most
    # useful field in the whole record for us, so it gets counted on its own.
    series = []
    for r in records:
        found = False
        for desc in r.get("description", []):
            match = re.match(r"\[([^\]]+)\]", desc.strip())
            if match:
                series.append(match.group(1))
                found = True
        if not found:
            series.append("(no bracketed series)")
    tally("description series", series, limit=30)

    rights = Counter(value for r in records for value in r.get("rights", ["(none)"]))
    print("-- rights --")
    for value, n in rights.most_common():
        print(f"  {n:5}  {value}")


# ---------------------------------------------------------------------------
# STAGE 2: choose what to keep
# ---------------------------------------------------------------------------
#
# The --report on the full 2,265 settled two questions that guesswork could not.
#
# 723 records are in the languages this project maps. Of those, 147 clear the US
# cutoff and 576 do not, and the split is not random: the material that clears is
# the 1910s Pathe series from the Russian empire (Tatar, Uzbek, Azerbaijani, Tajik,
# Turkmen) plus a handful of Arabic, Persian and Urdu sides, while almost everything
# that fails is the 1920s and 1930s North African and Turkish commercial catalogue.
#
# So this stage produces two outputs, not one:
#   gallica_selected.json   what we can harvest today
#   gallica_permission.md   what to ask the BnF for, by shelfmark
#
# The second is the more valuable document. An institutional request that says
# "339 Moroccan discs, shelfmarks listed" is a different kind of letter from one
# that says "we are interested in your collection".

# Three-letter codes from dc:language. The catalogue uses old-style MARC codes, so
# Persian is "per" rather than "fas" and Ottoman Turkish has its own code, "ota".
CORE_LANGUAGES = {
    "ara", "ota", "tur", "per", "fas", "kur",
    "uzb", "tgk", "tuk", "aze", "tat", "bak", "kaz", "kir", "uig",
    "urd", "snd", "pan", "pus", "ber", "kab", "tzm", "som", "hau", "ful",
    "mal", "ind", "msa", "may",
}

# Where a recording belongs, in the order we trust the evidence.
#
# The series is the librarian's classification and it names a country, not a studio.
# That distinction matters more here than anywhere else in this project, because the
# Archives de la Parole recorded VISITING PERFORMERS IN PARIS as well as buying
# commercial discs pressed abroad. Begum Fyzee-Rahamin sang for the Archives in 1914;
# she sang in Paris.
#
# So every placement here is placeBasis "tradition": this is where the music is from,
# not where the microphone stood. We already learned this lesson the expensive way
# with the Isfahan gazel, which the gazetteer filed in Iran because the makam shares
# a name with a city.
PLACES = [
    (r"Maroc",                    "Fez",       "Morocco",        34.0646,  -4.9737),
    (r"Alg[ée]rie",               "Algiers",   "Algeria",        36.7538,   3.0588),
    (r"Tunisie",                  "Tunis",     "Tunisia",        36.8065,  10.1815),
    (r"Egypte|Égypte",            "Cairo",     "Egypt",          30.0444,  31.2357),
    (r"Turquie",                  "Istanbul",  "Turkey",         41.0082,  28.9784),
    (r"Azerba[ïi]d[jz]an",        "Baku",      "Azerbaijan",     40.4093,  49.8671),
    (r"Tatars de Crim[ée]e|Crim[ée]e", "Bakhchysarai", "Crimea",  44.7539,  33.8619),
    (r"Tcherkess|Circass|Caucase",  "Nalchik",   "North Caucasus", 43.4981,  43.6189),
    (r"Tatars de Kazan|Kazan",    "Kazan",     "Tatarstan",      55.7963,  49.1064),
    (r"Sartes|Ouzb|Turkestan",    "Tashkent",  "Uzbekistan",     41.2995,  69.2401),
    (r"Tadjik",                   "Samarkand", "Tajik tradition",39.6270,  66.9750),
    (r"Turkm[ée]n",               "Ashgabat",  "Turkmenistan",   37.9601,  58.3261),
    (r"Afghan",                   "Kabul",     "Afghanistan",    34.5553,  69.2075),
    (r"Iran|Perse",               "Tehran",    "Iran",           35.6892,  51.3890),
    (r"Syrie",                    "Aleppo",    "Syria",          36.2021,  37.1343),
    (r"Madras|Chennai",           "Chennai",   "India",          13.0827,  80.2707),
    (r"Inde",                     "Delhi",     "India",          28.6139,  77.2090),
]

# Fallback when the series says nothing. Weaker evidence, so it is only reached
# second, and it is recorded as such in the record's notes.
LANGUAGE_PLACES = {
    "ota": ("Istanbul", "Turkey", 41.0082, 28.9784),
    "tur": ("Istanbul", "Turkey", 41.0082, 28.9784),
    "per": ("Tehran", "Iran", 35.6892, 51.3890),
    "fas": ("Tehran", "Iran", 35.6892, 51.3890),
    "aze": ("Baku", "Azerbaijan", 40.4093, 49.8671),
    "uzb": ("Tashkent", "Uzbekistan", 41.2995, 69.2401),
    "tgk": ("Samarkand", "Tajik tradition", 39.6270, 66.9750),
    "tuk": ("Ashgabat", "Turkmenistan", 37.9601, 58.3261),
    "tat": ("Kazan", "Tatarstan", 55.7963, 49.1064),
    "bak": ("Kazan", "Tatarstan", 55.7963, 49.1064),
    "kaz": ("Almaty", "Kazakhstan", 43.2380, 76.8829),
    "kir": ("Bishkek", "Kyrgyzstan", 42.8746, 74.5698),
    "uig": ("Kashgar", "Xinjiang, China", 39.4704, 75.9898),
    "urd": ("Delhi", "India", 28.6139, 77.2090),
    "snd": ("Karachi", "Pakistan", 24.8607, 67.0011),
    "pan": ("Lahore", "Pakistan", 31.5204, 74.3587),
    "mal": ("Kozhikode", "India", 11.2588, 75.7804),
}

RECITATION = re.compile(r"coran|qur.?an|sourate|surate|s[uū]ra[ht]?\b|tilawa|tajw", re.I)

# Two separate linguistic surveys are mixed into this collection, and neither is music.
#
# Hubert Pernot and Jean Poirot ran the phonetics side of the Archives in Paris. George
# Grierson's Linguistic Survey of India recorded the same parable in language after
# language across British India; "Parable of the prodigal son" appears dozens of times.
#
# But the exclusion cannot be blanket, and this is the part worth getting right. The
# Grierson discs are not uniformly speech: one of them is "[A country girl discards a
# prince lover] : [chant populaire en sindhi]", an actual folk song. So a record is only
# dropped when it looks like a survey AND says nothing about singing. A filter that
# throws away a song to be rid of a parable is not a filter, it is a loss.
SURVEY = re.compile(r"Pernot|Poirot|Grierson|Linguistic survey|dialecte|Conversation en|"
                    r"Les sons du|phon[ée]tique|Paroles prononc|Histoire de R[aâ]m|"
                    r"prodigal son|contes?\b|r[ée]cit\b", re.I)
MUSICAL = re.compile(r"\bchant|chanson|musique|\bair\b|danse|gazel|\u015farki|sarki|taxim|"
                     r"taksim|semai|mugham|maqam|makam|mawwal|moual|nawba|nouba", re.I)


def clean_title(fields: dict) -> str:
    raw = (fields.get("title") or [""])[0]
    return re.sub(r"^\[[^\]]*\]\.\s*,?\s*", "", raw).strip()


def year_bounds(fields: dict):
    """
    Turn Gallica's dot notation into (earliest, latest, how_precise).

    Returning the LATEST possible year is the whole point. Rights are judged by the
    worst case: if the last year a record could have been published still clears the
    cutoff, every earlier year does too. Returning the midpoint would invent a
    certainty the catalogue never claimed.
    """
    for raw in fields.get("date", []):
        text = raw.strip()
        if re.fullmatch(r"\d{4}", text):
            return int(text), int(text), "exact"
        if re.fullmatch(r"\d{3}\.", text):
            return int(text[:3] + "0"), int(text[:3] + "9"), "decade"
        if re.fullmatch(r"\d{2}\.\.", text):
            return int(text[:2] + "00"), int(text[:2] + "99"), "century"
    return None, None, "none"


def languages(fields: dict) -> list[str]:
    """Only the three-letter codes. The catalogue repeats each one in French prose."""
    return [v for v in fields.get("language", []) if re.fullmatch(r"[a-z]{3}", v)]


def place_for(fields: dict):
    """Return (city, country, lat, lng, basis_note) or None."""
    blob = " ".join(fields.get("description", []))
    for pattern, city, country, lat, lng in PLACES:
        if re.search(pattern, blob, re.I):
            return city, country, lat, lng, f"placed from the catalogue series ({city})"
    for code in languages(fields):
        if code in LANGUAGE_PLACES:
            city, country, lat, lng = LANGUAGE_PLACES[code]
            return city, country, lat, lng, (
                f"no country in the catalogue series; placed at {city} from the "
                f"language code '{code}' alone, which is weak evidence")
    return None


# The catalogue frequently states where and when the disc was cut, in a line like
#   "Enregistrement : (Algérie) Alger, 00-04-1929"
#   "Enregistrement : Paris, Université de Paris, La Sorbonne, 03-03-1914"
# This is the single most valuable field in the record and it is easy to miss, because
# it sits inside dc:description alongside the classification series.
#
# Note what it reveals: Begum Fyzee-Rahamin's Urdu songs were recorded in PARIS in 1914.
# The Archives de la Parole brought visiting performers to the Sorbonne as well as
# buying commercial discs pressed abroad. So a recording place and a tradition place are
# genuinely different facts here, and conflating them would repeat the Isfahan error on
# a much larger scale.
#
# We place by tradition and keep the recording location as a note. A map of traditions
# that put Indian song in Paris because that is where the microphone stood would be
# accurate and useless.
RECORDED_AT = re.compile(r"Enregistrement\s*:\s*(.+)", re.I)


def recording_note(fields: dict) -> str:
    for desc in fields.get("description", []):
        match = RECORDED_AT.search(desc)
        if match:
            return "recorded " + match.group(1).strip().rstrip(".")
    return ""


def shelfmark(fields: dict) -> str:
    for src in fields.get("source", []):
        match = re.search(r"\b(AP-[\w./-]+|[A-Z]{1,4}-\d[\w./-]*)", src)
        if match:
            return match.group(1)
    return ""


def select() -> None:
    if not RECORDS.exists():
        sys.exit("no gallica_records.json yet; run --search first")
    records = json.loads(RECORDS.read_text(encoding="utf-8"))

    keep, blocked, skipped = [], [], Counter()
    for fields in records:
        codes = languages(fields)
        if not any(code in CORE_LANGUAGES for code in codes):
            skipped["language outside this project"] += 1
            continue
        title = clean_title(fields)
        if SURVEY.search(title) and not MUSICAL.search(title):
            skipped["linguistic survey, not a performance"] += 1
            continue

        first, last, precision = year_bounds(fields)
        entry = {
            "ark": (fields.get("_ark") or [""])[0],
            "title": title,
            "date_raw": (fields.get("date") or [""])[0],
            "year_first": first, "year_last": last, "date_precision": precision,
            "languages": codes,
            "series": next((re.match(r"\[([^\]]+)\]", d.strip()).group(1)
                            for d in fields.get("description", [])
                            if re.match(r"\[([^\]]+)\]", d.strip())), ""),
            "creator": (fields.get("creator") or [""])[0],
            "publisher": (fields.get("publisher") or [""])[0],
            "shelfmark": shelfmark(fields),
            "recitation": bool(RECITATION.search(title)),
            "recorded_at": recording_note(fields),
        }

        if last is None:
            skipped["no usable date, so rights cannot be judged"] += 1
            continue
        if last > CUTOFF_YEAR:
            # Two different reasons land here and the letter should not blur them.
            # "1929" is provably inside copyright. "19.." might be 1908, we simply
            # cannot show that it is, and an unprovable claim is not a claim.
            entry["why"] = ("published after the cutoff" if first > CUTOFF_YEAR
                            else f"catalogue date '{entry['date_raw']}' is too vague "
                                 f"to establish a year")
            blocked.append(entry)
            continue

        placed = place_for(fields)
        if not placed:
            skipped["no place could be justified"] += 1
            continue
        entry["city"], entry["country"], entry["lat"], entry["lng"], entry["place_note"] = placed
        keep.append(entry)

    SELECTED.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    write_permission_list(blocked)

    print(f"{len(records)} catalogue records")
    for reason, n in skipped.most_common():
        print(f"  {n:5} skipped: {reason}")
    after = sum(1 for e in blocked if e.get("why", "").startswith("published"))
    print(f"  {len(blocked):5} in scope but not clearable -> {PERMISSION.name}")
    print(f"        ({after} provably after {CUTOFF_YEAR}, "
          f"{len(blocked) - after} too vaguely dated to establish)")
    print(f"  {len(keep):5} selected -> {SELECTED.name}")
    if keep:
        print(f"\n  by place: " + ", ".join(
            f"{city} {n}" for city, n in Counter(e["city"] for e in keep).most_common()))
        print(f"  recitation, will be quarantined: "
              f"{sum(1 for e in keep if e['recitation'])}")
        print(f"\n  roughly {len(keep) * 2} disc sides to download, "
              f"about {len(keep) * 2 * 2 / 1024:.1f} GB of source MP3")


def write_permission_list(blocked: list[dict]) -> None:
    """The BnF request, written as a document rather than a data file."""
    groups: dict[str, list[dict]] = {}
    for entry in blocked:
        groups.setdefault(entry["series"] or "(unclassified)", []).append(entry)

    lines = [
        "# Gallica material outside the US public domain",
        "",
        f"Generated by `gallica_harvester.py --filter`. {len(blocked)} recordings.",
        "",
        "Every record below is published on Gallica with `dc:rights = domaine public`,",
        "and every one is still under copyright in the United States, where this site is",
        "hosted. A foreign sound recording first published between 1923 and 1946 holds US",
        f"protection for 100 years from publication, so the cutoff today is {CUTOFF_YEAR}.",
        "French expiry does not transfer.",
        "",
        "This is therefore not a list of problems. It is the specific ask for the BnF:",
        "named discs, with shelfmarks, that the library has already digitised and already",
        "considers public domain in France.",
        "",
    ]
    for series, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        years = sorted({e["date_raw"] for e in items if e["date_raw"]})
        lines.append(f"## {series} ({len(items)} recordings, {years[0]}-{years[-1]})"
                     if years else f"## {series} ({len(items)} recordings)")
        lines.append("")
        lines.append("| shelfmark | date | why | title | ark |")
        lines.append("|---|---|---|---|---|")
        for entry in sorted(items, key=lambda e: e["date_raw"]):
            title = entry["title"].replace("|", "/")[:70]
            why = "after cutoff" if entry.get("why", "").startswith("published") else "undatable"
            lines.append(f"| {entry['shelfmark']} | {entry['date_raw']} | {why} | {title} | "
                         f"{entry['ark']} |")
        lines.append("")
    PERMISSION.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# STAGE 3: fetch the audio and join it to the pipeline
# ---------------------------------------------------------------------------

AUDIO_DIR = SCRIPT_DIR / "sawt_audio"
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"


def sides_of(ark: str) -> list[str]:
    """Ask the record service which audio files a disc actually has."""
    root = get_xml(OAI_RECORD, {"ark": ark.split("/")[-1]})
    return [node.text for node in root.findall(".//sounds//file") if node.text]


def download(url: str, target: Path, max_mb: float = 60.0) -> tuple[bool, str]:
    """
    Stream one file to disk, writing to a .part and renaming only on success.

    The rename is the whole trick. A half-written file that carries its final name
    looks finished to the next run, which skips it forever. Renaming last means a
    file either does not exist or is complete, with no third state. We have already
    shipped this bug twice in this project, once in the downloader and once in the
    transcoder, so it is written out rather than remembered.

    timeout is a (connect, read) pair. A single number would apply per read, and with
    stream=True a stalled server can hold a connection open indefinitely between
    chunks while never breaching a per-read limit.
    """
    partial = target.with_suffix(target.suffix + ".part")
    try:
        with requests.get(url, headers={**HEADERS, "Accept": "*/*"},
                          stream=True, timeout=(10, 40)) as response:
            if response.status_code != 200:
                return False, f"HTTP {response.status_code}"
            written = 0
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    written += len(chunk)
                    if written > max_mb * 1_048_576:
                        handle.close()
                        partial.unlink(missing_ok=True)
                        return False, f"larger than {max_mb:.0f}MB"
                    handle.write(chunk)
        if written < 4096:
            partial.unlink(missing_ok=True)
            return False, f"only {written} bytes, not audio"
        partial.replace(target)
        return True, f"{written / 1_048_576:.1f}MB"
    except requests.RequestException as err:
        partial.unlink(missing_ok=True)
        return False, str(err)[:90]


def performer_of(entry: dict) -> str:
    """Prefer the catalogue's creator field; fall back to what follows the slash."""
    if entry.get("creator"):
        return re.sub(r"\s*\([^)]*\)\s*", " ", entry["creator"]).strip(" .,;")
    if "/" in entry["title"]:
        tail = entry["title"].split("/", 1)[1]
        return re.split(r"[;.]", tail)[0].strip()
    return ""


def fetch(limit: int | None) -> None:
    if not SELECTED.exists():
        sys.exit("no gallica_selected.json yet; run --filter first")
    selected = json.loads(SELECTED.read_text(encoding="utf-8"))
    records = json.loads(CANDIDATES.read_text(encoding="utf-8")) if CANDIDATES.exists() else []
    known = {c["page_url"] for c in records}
    AUDIO_DIR.mkdir(exist_ok=True)

    outstanding = [e for e in selected
                   if not any(f"{e['ark']}/f" in url for url in known)]
    # Count what is done BEFORE --limit trims the batch. The first version subtracted
    # the trimmed list from the total and reported "6 already fetched" on a run that
    # had fetched nothing, because it was counting "not in this batch" as "done". A
    # progress line that lies about progress is worse than no progress line.
    todo = outstanding[:limit] if limit else outstanding
    print(f"{len(selected)} selected, {len(selected) - len(outstanding)} already fetched, "
          f"{len(outstanding)} outstanding, {len(todo)} in this batch")

    added = failed = 0
    for index, entry in enumerate(todo, 1):
        ark = entry["ark"]
        stem = ark.split("/")[-1]
        print(f"[{index}/{len(todo)}] {entry['title'][:56]}")
        try:
            urls = sides_of(ark)
        except requests.RequestException as err:
            print(f"    could not list sides: {err}")
            failed += 1
            continue
        time.sleep(PAUSE_SECONDS)

        for side, url in enumerate(urls, 1):
            page_url = f"https://gallica.bnf.fr/{ark}/f{side}"
            if page_url in known:
                continue
            target = AUDIO_DIR / f"gallica_{stem}_f{side}.mp3"
            if target.exists() and target.stat().st_size > 4096:
                ok, message = True, "already on disk"
            else:
                print(f"    side {side} ...", end=" ", flush=True)
                ok, message = download(url, target)
                print(message)
                time.sleep(PAUSE_SECONDS)
            if not ok:
                failed += 1
                continue

            # The disc title names both sides, often as "A ; B / performer". Splitting
            # on the semicolon is tempting and wrong: "Sarhadi / Mogamed Ali, chant ;
            # s akk. dejra" uses the same separator for the ACCOMPANIMENT. A wrong
            # split silently mislabels a recording, which is worse than a long title,
            # so the whole title is kept and the side is marked.
            records.append({
                "source": "gallica",
                "title": f"{entry['title']} [side {side}]",
                "page_url": page_url,
                "audio_url": url,
                "local_audio": str(Path("sawt_audio") / target.name).replace("\\", "/"),
                "license": (f"Public domain (BnF: domaine public; US: published "
                            f"{entry['year_last']}, before the {CUTOFF_YEAR} cutoff)"),
                "year": entry["year_last"],
                "lat": entry["lat"], "lng": entry["lng"],
                "place_basis": "tradition",
                "geocoded_from": entry["place_note"],
                "attribution": performer_of(entry),
                "tier": "A",
                "found_by": "gallica: BnF Archives de la Parole",
                # A LIST, not a string. Every other script in this pipeline treats
                # notes as a list (gazetteer.py appends to it), and genres.py does
                # " ".join(notes). Handing it a string would not crash: join would
                # iterate the characters and produce "c a t a l o g u e", quietly
                # destroying every keyword match. Silent wrong beats loud wrong only
                # for the person who never reads the output.
                "notes": [part for part in [
                    f"catalogue date '{entry['date_raw']}' "
                    f"({entry['year_first']}-{entry['year_last']}, {entry['date_precision']})",
                    f"BnF shelfmark {entry['shelfmark']}" if entry["shelfmark"] else "",
                    entry.get("recorded_at", ""),
                    f"label: {entry['publisher']}" if entry.get("publisher") else "",
                    entry["place_note"],
                ] if part],
                **({"category": "recitation",
                    "category_basis": "title names a sura or recitation"}
                   if entry["recitation"] else {}),
            })
            known.add(page_url)
            added += 1

        CANDIDATES.write_text(json.dumps(records, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    size = sum(f.stat().st_size for f in AUDIO_DIR.iterdir() if f.is_file()) / 1_048_576
    print(f"\n{added} sides added, {failed} failed. "
          f"sawt_audio/ now holds {size:.0f}MB across {len(list(AUDIO_DIR.iterdir()))} files.")
    if added:
        print("\nNext: python make_web_audio.py   then  python review.py")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe", action="store_true",
                        help="check the API and one audio download, change nothing")
    parser.add_argument("--search", action="store_true",
                        help="page the whole catalogue into gallica_records.json")
    parser.add_argument("--report", action="store_true",
                        help="summarise what the catalogue actually contains")
    parser.add_argument("--filter", action="store_true", dest="filter_",
                        help="choose what to keep, and list what needs permission")
    parser.add_argument("--fetch", action="store_true",
                        help="download the selected audio into sawt_audio/")
    parser.add_argument("--limit", type=int, default=None,
                        help="with --fetch, stop after this many discs")
    args = parser.parse_args()

    if not (args.probe or args.search or args.report or args.filter_ or args.fetch):
        parser.print_help()
        return

    # keep_awake returns a bool, it is not a context manager. Writing
    # "with keep_awake(...)" would raise TypeError on the first line of a run that
    # otherwise looks fine, which is the worst place for a typo to hide.
    keep_awake("the Gallica harvest")
    if args.probe:
        probe()
    if args.search:
        search()
    if args.report:
        report()
    if args.filter_:
        select()
    if args.fetch:
        fetch(args.limit)


if __name__ == "__main__":
    main()
