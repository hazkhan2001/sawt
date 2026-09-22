"""
genres.py
Sort each recording into a family and a genre, from its title, tags and search term.

Two levels, because the map needs both:
  family  decides the COLOUR   (three families, because three is the most a map can
                                colour-code and still be readable, see make_globe.py)
  genre   decides the SHAPE and the label (seven, which is what you actually asked for)

Run on its own to see how the current results classify:
    python genres.py
"""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"


def fold(text: str) -> str:
    """
    Strip accents so "bağlama", "Dəşti" and "müezzin" compare as plain letters.

    NFKD splits a letter into base + combining mark ("ğ" becomes "g" + a caron), and
    the category "Mn" is exactly those marks, so dropping them leaves the base letter.
    Two characters have no decomposition and need doing by hand: Azeri schwa "ə" and
    Turkish dotless "ı".
    """
    text = text.lower().replace("ə", "e").replace("ı", "i").replace("ø", "o")
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9؀-ۿЀ-ӿ]+", " ", stripped)


# genre key, family, label, and the words that identify it.
# ORDER MATTERS: the first match wins, so the most specific genre comes first.
# "Sufi zikr song Nakshibandi -Naat" contains both zikr and naat; dhikr is the
# better description of what the recording is, so dhikr is tested first.
GENRE_RULES = [
    ("tilawa", "recitation", "Quran recitation", (
        "quran", "qur an", "koran", "coran", "tilawa", "tilawah", "tajwid", "tajweed",
        "mujawwad", "murattal", "qari", "qiraat", "surah", "surat al", "ayat",
        "mengaji", "ngaji", "قران", "قرآن", "تلاوه", "تلاوة", "коран")),

    ("adhan", "call", "Adhan and call to prayer", (
        "adhan", "adzan", "azan", "azaan", "athan", "ezan", "muezzin", "muazzin",
        "mu azzin", "moazzen", "call to prayer", "calltoprayer", "call for prayer",
        "prayer call", "minaret", "azzan", "adan",
        # Field recordists label in their own language. These cost nothing to add
        # and recovered 20-odd recordings that were sitting in "Other".
        "appel a la priere", "appel a la prier", "gebetsruf", "ruf des muezzin",
        "llamada a la oracion", "oracion", "chiamata alla preghiera", "gebedsoproep",
        "اذان", "مؤذن", "موذن", "азан", "муэдзин")),

    ("dhikr_hadra", "devotional", "Sufi dhikr and hadra", (
        "dhikr", "zikr", "zikir", "hadra", "hadhra", "sema", "semazen", "mevlevi",
        "mevlana", "whirling", "tasavvuf", "tasawwuf", "sufi", "naqshbandi",
        "nakshibandi", "naqshibandi", "haqqani", "qadiri", "chishti", "tariqa",
        "dergah", "tekke", "zawiya", "zaviye", "moulid", "mawlid", "mevlut",
        "ذكر", "ذکر", "حضره", "صوفي", "صوفی", "تصوف", "зикр", "суфи")),

    ("inshad_madih", "devotional", "Nasheed, ilahi and madih", (
        "nasheed", "nashid", "anasheed", "anashid", "ilahi", "naat", "na t",
        "qawwali", "qawali", "qawwal", "qasida", "qasidah", "kaside", "kasidah",
        "sholawat", "selawat", "salawat", "madih", "inshad", "tekbir", "hymn",
        "نشيد", "اناشيد", "قوالي", "مولد")),

    ("art_music", "music", "Maqam, mugham and modal music", (
        "maqam", "makam", "mugham", "mugam", "muqam", "dastgah", "nawbah", "nuba",
        "taqsim", "taksim", "segah", "rast", "bayati", "bayat", "hicaz", "huzzam",
        "mahur", "shahnaz", "sahnaz", "arazbari", "heyrati", "mansuriyye",
        "vilayeti", "simayi", "dashti", "desti", "tesnifi", "tasnif", "xumar",
        "gazel", "gazal", "ghazal", "sanat muzigi", "fasil",
        "qaryagdioglu", "garyagdioglu", "karyagdi", "garyagdy", "khanende",
        "xanende", "semaisi", "semayissi", "مقام", "دستگاه", "мугам",
        # Added for the Gallica 78s. The BnF catalogued them from the disc labels,
        # so the mode names arrive in French and Russian transliteration: "usak" for
        # ushshaq, "moual" for mawwal, "nihavend" for nihavent. Same repertoire,
        # different spelling conventions, and without these the whole Archives de la
        # Parole harvest classifies as "other".
        "usak", "ushaq", "ussak", "taslib", "sarang", "shashmaqam", "shashmaqom",
        "moual", "mawwal", "mawal", "nihavend", "nihavent", "sevkefza", "sarki",
        "sharki", "nouba", "muwashshah", "mouachah", "aroubi", "hawzi", "haouzi",
        "ksida", "qsida", "chaabi", "sanaa", "gharnati", "malouf", "maalouf")),

    ("instrument", "music", "Instrument and solo playing", (
        "oud", "ud ", "ney", "nay", "duduk", "balaban", "kanun", "qanun", "qanoun",
        "saz", "baglama", "tanbur", "tambur", "dutar", "santur", "sanatur",
        "kamancha", "kamancheh", "kemence", "zurna", "davul", "bendir", "kudum",
        "darbuka", "riq", "daf", "rebab", "gambus", "lute", "سنتور", "كمانچه",
        "dejra", "dejre", "dayra", "daire", "dayereh", "doira", "ghaita", "ghaitas",
        "guembri", "gimbri", "qraqeb", "karkabou", "sorna", "surnay")),
]

GENRE_RULES.append(
    ("ambience", "other", "Mosque and street ambience", (
        "mosque", "masjid", "mosquee", "mosqué", "moschee", "mezquita", "cami",
        "camii", "mescit", "khanqah", "dargah", "shrine", "ambience", "ambiance",
        "soundwalk", "sound walk", "stadtambi", "بمسجد", "مسجد", "мечет")))


# Provenance is evidence too.
#
# The Gallica selection is commercial 78rpm discs from the BnF's "Traditions" series,
# already filtered to drop the linguistic-survey recordings. What is left is
# overwhelmingly traditional art music, so a Gallica record that matched no keyword is
# far more likely to be art music than to be "other". The catalogue simply spells the
# mode names in ways no keyword list will ever fully cover.
#
# This is a guess and it is labelled as one: every Gallica record goes through the same
# human review as everything else, and review is where a wrong guess gets corrected.
SOURCE_DEFAULTS = {"gallica": ("art_music", "music", "Maqam, mugham and modal music")}


FAMILY_LABEL = {
    "call": "Call to prayer",
    "devotional": "Devotional voice",
    "music": "Modal and instrumental",
    "recitation": "Quran recitation",
    "other": "Other and ambience",
    # "ambience" shares the "other" family colour: it is context, not a tradition.
}


def classify(candidate: dict) -> tuple[str, str, str]:
    """Return (genre key, family key, human label) for one candidate."""
    # The harvester already flagged recitation at search time. Trust that first:
    # it is a deliberate quarantine decision, not a guess from the title.
    if candidate.get("category") == "recitation":
        return "tilawa", "recitation", "Quran recitation"

    # notes is a list by convention. If a caller hands us a string, " ".join would
    # iterate its CHARACTERS and turn "catalogue" into "c a t a l o g u e", which
    # matches nothing and raises nothing. Normalising here costs one line and closes
    # a failure that is invisible from the outside.
    notes = candidate.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]

    haystack = fold(" ".join([
        candidate.get("title", ""),
        candidate.get("found_by") or "",
        " ".join(notes),
    ]))

    for genre, family, label, words in GENRE_RULES:
        for word in words:
            folded = fold(word).strip()
            if not folded:
                continue
            # Word-boundary for short Latin words, plain substring for Arabic and
            # Cyrillic, for the same reason as the harvester's match modes.
            pattern = rf"\b{re.escape(folded)}\b" if folded.isascii() else re.escape(folded)
            if re.search(pattern, haystack):
                return genre, family, label

    # No keyword matched. Before giving up, ask where the record came from.
    source = candidate.get("source")
    if source in SOURCE_DEFAULTS:
        return SOURCE_DEFAULTS[source]
    return "other", "other", "Other and ambience"


def main() -> None:
    if not CANDIDATES.exists():
        raise SystemExit(f"No results at {CANDIDATES}.")
    items = json.loads(CANDIDATES.read_text(encoding="utf-8"))

    counts, family_counts = Counter(), Counter()
    for c in items:
        genre, family, label = classify(c)
        counts[label] += 1
        family_counts[FAMILY_LABEL[family]] += 1

    print(f"{len(items)} candidates\n")
    print("by genre (shape on the map):")
    for label, n in counts.most_common():
        print(f"  {n:>4}  {label}")
    print("\nby family (colour on the map):")
    for label, n in family_counts.most_common():
        print(f"  {n:>4}  {label}")

    print("\nA sample of what landed in 'Other', to check the rules are not too narrow:")
    shown = 0
    for c in items:
        if classify(c)[0] == "other" and shown < 20:
            print(f"  {c['title'][:74]}")
            shown += 1


if __name__ == "__main__":
    main()
