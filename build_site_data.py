"""
build_site_data.py
Turn the approved recordings into the validated JSON the website will consume.

This is spec task 8, and it is the most important file in the pipeline, because it
is the CONTRACT. Everything upstream is allowed to be messy: harvesters guess,
gazetteers infer, reviewers change their minds. Everything downstream, the Next.js
app, assumes its data is correct. This script is the wall between the two.

The wall is built out of pydantic. A pydantic model is a class where each field
declares its type and its rules, and constructing one either produces a valid object
or raises an error saying exactly which field failed and why. That turns "we should
remember to check attribution on CC BY items" into "a CC BY item without attribution
cannot be built". The check stops depending on anyone remembering.

Needs:  pip install pydantic
Run:    python build_site_data.py
Writes: site/hubs.json, site/tracks.json
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Literal, Optional

try:
    from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
except ImportError:
    raise SystemExit("This step needs pydantic:\n    pip install pydantic")

from genres import classify
from gazetteer import nearest_place
from hub_essays import HUB_ESSAYS

SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"   # the source of truth
APPROVED = SCRIPT_DIR / "sawt_approved.json"      # written by review.py, read by nobody
REVIEWS = SCRIPT_DIR / "sawt_reviews.json"
SITE_DIR = SCRIPT_DIR / "site"
CUTOFF_YEAR = date.today().year - 101

# The curated anchors from the spec, plus the places the data itself argued for.
# An anchor gets a written essay; every other place is generated and carries none.
ANCHOR_HUBS = {
    "fez": ("Fez", "Morocco", 34.0646, -4.9737),
    "cairo": ("Cairo", "Egypt", 30.0444, 31.2357),
    "aleppo": ("Aleppo", "Syria", 36.2021, 37.1343),
    "konya": ("Konya", "Turkey", 37.8746, 32.4932),
    "isfahan": ("Isfahan", "Iran", 32.6539, 51.6660),
    "delhi": ("Delhi", "India", 28.6139, 77.2090),
    "kashgar": ("Kashgar", "Xinjiang, China", 39.4704, 75.9898),
    "istanbul": ("Istanbul", "Turkey", 41.0082, 28.9784),
    "marrakech": ("Marrakech", "Morocco", 31.6295, -7.9811),
    "shusha": ("Shusha", "Karabakh", 39.7578, 46.7464),
}

# genres.py keys map onto the spec's Genre union. "instrument" has no slot of its
# own, so it folds into art_music and keeps its detail in subGenre rather than
# inventing a value the TypeScript does not know about.
# A typo in an essay key would be invisible: the essay simply never attaches and the
# hub ships blank. Checking at import turns a silent blank into a startup error.
_orphans = set(HUB_ESSAYS) - set(ANCHOR_HUBS)
if _orphans:
    raise SystemExit(f"hub_essays.py has entries for non-anchor hubs: {sorted(_orphans)}")


GENRE_MAP = {
    "adhan": "adhan", "tilawa": "tilawa", "dhikr_hadra": "dhikr_hadra",
    "inshad_madih": "inshad_madih", "art_music": "art_music",
    "instrument": "art_music", "ambience": "ambience", "other": "other",
}


# Dates that scholarship supplies and the file metadata does not.
#
# Three approved recordings carry a bare "Public domain" tag and no year, which
# validation refuses: a public-domain claim only clears if the date clears, and
# without a year we cannot say it does. But these are Jabbar Garyagdioglu, the
# Karabakh mugham master, and his gramophone sides were cut between 1906 and 1912.
# That is comfortably before the 1925 US cutoff, so the claim is sound; it just
# needs the fact written down.
#
# A range rather than a point, because "1906-1912" is what is actually known, and
# recording the midpoint as if it were a date would be a small invented certainty.
# dateBasis "catalogue" says the date came from a catalogue and not from the
# recordist, which is the same honesty the placeBasis field already provides.
KNOWN_DATES = [
    (("qaryagdioglu", "garyagdioglu", "karyagdi", "garyagdy", "qarya", "jabbar", "cabbar"),
     (1906, 1912), "Karabakh mugham, recorded on gramophone discs 1906-1912"),
]


# Findings from reading the actual archive pages, rather than the one-word licence
# string the harvester scraped off them.
#
# Both records below arrived tagged "Public domain" with a year that failed the
# cutoff test, and both looked like the same problem. They are not the same problem,
# and the difference is exactly why a bare licence string is not enough to publish on.
#
# Keyed on a fragment of the source URL, because a URL is an identifier and a title
# is a label someone can retype.
RIGHTS_FINDINGS = {
    "Husseyni_Saz_Semayissi": {
        "basis": "pdm",
        "license": "Public Domain Mark 1.0 (Commons: PD-old-70 + PD-US-expired; BnF: domaine public)",
        "years": (1911, 1937),
        "performer": "Hafiz Kemal Bey (kemence), Hayriye Hanim (oud)",
        "archival": "https://gallica.bnf.fr/ark:/12148/bpt6k1310275k",
        "note": ("Pathe 78rpm disc, matrices N 11016 and N 11017, from the Pathe donation "
                 "to the Archives de la Parole; BnF Audiovisuel AP-3029, digitised as "
                 "Gallica ark:/12148/bpt6k1310275k, where the BnF declares it domaine "
                 "public. The Commons page carries the CC Public Domain Mark alongside "
                 "PD-old-70 and a US pre-1931 publication tag. Its '1939' is the "
                 "performer's death year used as an upper bound, not a recording date; "
                 "the donation itself spans 1911 to 1937, which is what is actually known."),
    },
    "Gul_achdi_by_Jabbar_Garyagdy": {
        "basis": None,
        "note": ("Refused, and expected to stay refused until the 2030s. The Commons page "
                 "carries {{PD-Azerbaijan}} and nothing else, and that template says in "
                 "its own text that a United States public domain tag is still required. "
                 "None is present. The date given is '1930s', and a foreign sound "
                 "recording first published then holds US protection for 100 years from "
                 "publication. Azerbaijani expiry does not transfer. The file stays on "
                 "disk; it does not go on the site."),
    },
}


def rights_finding(source_url: str):
    """Return the scholarship finding for a source URL, or None."""
    for key, finding in RIGHTS_FINDINGS.items():
        if key in source_url:
            return finding
    return None


def known_date(title: str):
    """Return ((first, last), note) for a recording whose date is known from scholarship."""
    lowered = title.lower()
    for keys, years, note in KNOWN_DATES:
        if any(key in lowered for key in keys):
            return years, note
    return None, ""


def slug(text: str) -> str:
    """A url-safe, stable id. Stable matters: it is a foreign key, not a label."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-")


def rights_basis(license_name: str, year: Optional[int]) -> Optional[str]:
    """Map a licence string onto the spec's RightsBasis, or None if it needs a human."""
    lic = (license_name or "").lower()
    if "cc0" in lic or "zero" in lic:
        return "cc0"
    if "sa" in lic.replace("-", " ").split():
        return "cc-by-sa"
    if "mark" in lic:
        return "pdm"
    if "public domain" in lic:
        # A bare "public domain" only clears if the date does. Without a year we
        # cannot say it does, so we refuse rather than assume.
        return "pd-us-published-pre-cutoff" if year and year <= CUTOFF_YEAR else None
    if "by" in lic.replace("-", " ").split() or lic.startswith("cc by"):
        return "cc-by"
    return None


class SoundHub(BaseModel):
    id: str
    name: str
    country: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    description: str = ""
    historicalContext: str = ""
    isAnchor: bool = False
    trackCount: int = 0


class SoundTrack(BaseModel):
    id: str
    hubId: str
    title: str = Field(min_length=1)
    performerOrZawiya: str = ""
    genre: Literal["art_music", "qawwali", "dhikr_hadra", "inshad_madih", "nawbah",
                   "adhan", "tilawa", "ambience", "other"]
    subGenre: str = ""
    instrumentation: list[str] = []
    audioUrl: str = Field(min_length=1)
    archivalUrl: Optional[str] = None
    durationSeconds: Optional[float] = None
    recordedYear: Optional[int] = None
    yearRange: Optional[list[int]] = None      # for material dated only to an era
    dateBasis: Literal["stated", "catalogue", "estimated", "unknown"] = "unknown"
    placeBasis: Literal["geotag", "title", "tradition"] = "geotag"
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    rightsBasis: Literal["cc0", "cc-by", "cc-by-sa", "pdm",
                         "pd-us-published-pre-cutoff", "own_recording",
                         "permission", "stream_only"]
    license: str
    attribution: Optional[str] = None
    sourceUrl: str
    contextNotes: str = ""

    @field_validator("audioUrl")
    @classmethod
    def must_be_self_hosted(cls, value: str) -> str:
        # Rule 10. A track whose audio still points at someone else's server is not
        # ready to ship, and the only reliable way to enforce that is to refuse it here.
        if value.startswith("http"):
            raise ValueError("audioUrl still points at a remote server (rule 10: self-host)")
        return value

    @model_validator(mode="after")
    def attribution_required_for_by(self):
        # CC BY makes credit a CONDITION of the licence, not a courtesy. Publishing
        # without it is infringement, so it is an error and not a warning.
        if self.rightsBasis in ("cc-by", "cc-by-sa") and not (self.attribution or "").strip():
            raise ValueError(f"{self.rightsBasis} requires an attribution line")
        return self


def build() -> tuple[list, list, list]:
    """
    Read from the SOURCE OF TRUTH, not from a snapshot of it.

    sawt_approved.json is a derived file: a copy of the records as they looked the
    moment you ran --export. Every later step that enriches a record, downloading its
    audio, transcoding it, fixing its coordinates, updates sawt_candidates.json and
    leaves that copy behind. Building from the copy meant 37 tracks kept failing the
    self-hosting check hours after their files were sitting on disk.

    The fix is not to remember to re-export. It is to stop depending on the snapshot:
    take the records from sawt_candidates.json and the verdicts from
    sawt_reviews.json, and join them. A derived file cannot go stale if nothing reads it.
    """
    reviews = json.loads(REVIEWS.read_text(encoding="utf-8")) if REVIEWS.exists() else {}
    records = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    approved = [c for c in records
                if reviews.get(c["page_url"], {}).get("decision") == "approve"]

    hubs: dict[str, SoundHub] = {}
    for key, (name, country, lat, lng) in ANCHOR_HUBS.items():
        # .get with a default means an anchor added before its essay is written
        # still builds, it just carries empty strings, which is the model default.
        essay = HUB_ESSAYS.get(key, {})
        hubs[key] = SoundHub(id=key, name=name, country=country, lat=lat, lng=lng,
                             isAnchor=True,
                             description=essay.get("description", ""),
                             historicalContext=essay.get("historicalContext", ""))

    tracks, problems, quarantined = [], [], []
    for c in approved:
        source_ref = c["page_url"]
        near = nearest_place(c["lat"], c["lng"]) if c.get("lat") is not None else None

        # Which hub? An anchor if one is close, otherwise a hub named for this place.
        hub_id = None
        if near:
            candidate = slug(re.sub(r"\s*\([^)]*\)$", "", near["city"]))
            if candidate in hubs and hubs[candidate].isAnchor and near["km"] <= 350:
                hub_id = candidate
            else:
                hub_id = candidate
                hubs.setdefault(hub_id, SoundHub(
                    id=hub_id, name=near["city"], country=near["country"],
                    lat=c["lat"], lng=c["lng"]))
        if not hub_id:
            hub_id = "unplaced"
            hubs.setdefault(hub_id, SoundHub(id=hub_id, name="Unplaced", country="",
                                             lat=c["lat"], lng=c["lng"]))

        # Fill a missing year from scholarship before the rights test runs.
        years, date_note = known_date(c["title"])
        year = c.get("year")
        year_range = None
        date_basis = "catalogue" if year else "unknown"
        if not year and years:
            year_range = list(years)
            year = years[1]          # judge rights by the LATEST possible year: if the
            date_basis = "catalogue"  # last plausible date clears the cutoff, all do

        genre_key, _family, label = classify(c)

        # The recitation quarantine, made explicit.
        #
        # Until now it worked by accident: the harvester tagged recitation searches and
        # nothing so tagged was ever approved, so no tilawa record reached this point and
        # the exclusion was never tested. Then four recordings titled as calls to prayer
        # turned out, on listening, to be Quran recitation, and they would have shipped
        # onto the map under the adhan colour. An invariant that holds because its case
        # never came up is not an invariant.
        #
        # So the skip is written down. Recitation is kept, downloaded and reviewed like
        # everything else; it just does not go on the map, because presenting it as one
        # more coloured dot beside the instrumental music is not a decision to make by
        # default. Relaxing this later means deleting four lines, which is the right
        # amount of effort for that decision.
        if genre_key == "tilawa":
            quarantined.append({"title": c["title"], "source": source_ref})
            continue

        audio = c.get("web_audio") or c.get("local_audio") or c.get("audio_url") or ""
        note = (reviews.get(source_ref) or {}).get("note", "")

        # A finding from reading the archive page beats anything inferred from the
        # scraped licence string. A finding with basis None is a deliberate refusal,
        # and it short-circuits: no point validating a record we have decided not to
        # publish, and the refusal reason is more useful than a validator message.
        finding = rights_finding(source_ref)
        basis = rights_basis(c.get("license"), year)
        licence_text = c.get("license") or ""
        performer = c.get("attribution") or ""
        archival = c.get("archival_audio") or c.get("local_audio") or None
        if finding:
            if finding["basis"] is None:
                problems.append({"title": c["title"], "source": source_ref,
                                 "reasons": [finding["note"]]})
                continue
            basis = finding["basis"]
            licence_text = finding.get("license", licence_text)
            performer = finding.get("performer", performer)
            archival = finding.get("archival", archival)
            if finding.get("years"):
                year_range = list(finding["years"])
                year = finding["years"][1]
                date_basis = "catalogue"
            date_note = finding["note"]

        context = " ".join(part for part in [note, date_note] if part)

        try:
            tracks.append(SoundTrack(
                id=f"{c['source'][:2]}-{slug(source_ref.rstrip('/').split('/')[-1] or c['title'])}",
                hubId=hub_id,
                title=c["title"],
                performerOrZawiya=performer,
                genre=GENRE_MAP[genre_key],
                subGenre=label,
                audioUrl=str(audio).replace("\\", "/"),
                archivalUrl=archival,
                durationSeconds=c.get("duration_seconds"),
                recordedYear=year,
                yearRange=year_range,
                dateBasis=date_basis,
                placeBasis=c.get("place_basis") or "geotag",
                lat=c["lat"], lng=c["lng"],
                rightsBasis=basis,
                license=licence_text,
                attribution=performer or None,
                sourceUrl=source_ref,
                contextNotes=context,
            ))
        except (ValidationError, ValueError) as err:
            reasons = []
            if isinstance(err, ValidationError):
                for issue in err.errors():
                    field = ".".join(str(p) for p in issue["loc"]) or "?"
                    reasons.append(f"{field}: {issue['msg']}")
            else:
                reasons.append(str(err))
            problems.append({"title": c["title"], "source": source_ref, "reasons": reasons})

    for track in tracks:
        hubs[track.hubId].trackCount += 1
    live_hubs = [h for h in hubs.values() if h.trackCount or h.isAnchor]
    return live_hubs, tracks, problems, quarantined


def main() -> None:
    parser = argparse.ArgumentParser(description="Build validated site data from approved records.")
    parser.add_argument("--write", action="store_true",
                        help="write site/hubs.json and site/tracks.json (default is a dry run)")
    args = parser.parse_args()

    hubs, tracks, problems, quarantined = build()
    print(f"{len(tracks)} tracks validated, {len(problems)} rejected by validation")
    print(f"{len(hubs)} hubs ({sum(1 for h in hubs if h.isAnchor)} curated anchors, "
          f"{sum(1 for h in hubs if not h.isAnchor)} generated from place names)")

    if quarantined:
        print(f"\n{len(quarantined)} approved records held back as Quran recitation:")
        for item in quarantined:
            print(f"    {item['title'][:68]}")
        print("  Kept on disk, kept out of the map. See the quarantine note in build().")

    empty = [h for h in hubs if h.isAnchor and not h.trackCount]
    if empty:
        print(f"\nAnchor hubs with nothing in them: {', '.join(h.name for h in empty)}")
        print("  Kept on purpose: an empty hub is an honest statement about the archives.")

    if problems:
        print(f"\n{len(problems)} records could NOT be turned into tracks:\n")
        from collections import Counter
        tally = Counter(r.split(":")[0] if ":" in r else r
                        for p in problems for r in p["reasons"])
        for reason, n in tally.most_common():
            print(f"  {n:>4}  {reason}")
        print("\n  first five:")
        for p in problems[:5]:
            print(f"    {p['title'][:52]}")
            for r in p["reasons"]:
                print(f"       {r}")

    if not args.write:
        print("\nDry run. Add --write to produce site/hubs.json and site/tracks.json.")
        return

    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / "hubs.json").write_text(
        json.dumps([h.model_dump() for h in sorted(hubs, key=lambda h: -h.trackCount)],
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (SITE_DIR / "tracks.json").write_text(
        json.dumps([t.model_dump() for t in tracks], ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\nWrote site/hubs.json ({len(hubs)}) and site/tracks.json ({len(tracks)}).")


if __name__ == "__main__":
    main()
