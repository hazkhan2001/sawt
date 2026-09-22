"""
gazetteer.py
Recover coordinates from titles that name a place.

Many recordings say where they are and carry no geotag:
    "Muezzin, Marrakech"
    "Call to Prayer, Old Dehli.wav"
    "Adhan at Night, Galata Istanbul"
    "Ancien Medina, Essaouira, Maroc - Battlements and Muezzin"

A gazetteer is just a list of place names with coordinates. The interesting part is
not the list, it is refusing to guess: a wrong dot on a map is worse than no dot,
because no dot is visibly missing and a wrong dot looks like data.

Run:  python gazetteer.py            (dry run: shows what it would do, changes nothing)
      python gazetteer.py --apply    (writes coordinates into sawt_candidates.json)
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from sawt_harvester import normalize_text      # one normaliser, used everywhere

SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"

# Place names that are really common nouns, and would produce confident nonsense.
#   "medina" is Arabic for "city" and names the old quarter of every Maghrebi town,
#   so "Ancien Medina, Essaouira" is in Morocco, not Saudi Arabia.
#   "masjid", "jami", "kasbah", "souk" are building types, not places.
NEVER_A_PLACE = {"medina", "medinah", "médina", "masjid", "jami", "jamaa",
                 "kasbah", "casbah", "souk", "souq", "bazaar", "mosque"}

# Place names that are ALSO the names of musical modes. This is a trap peculiar to
# this project: the maqam and makam repertoire is full of place names, because modes
# were named after the regions their sound was associated with. Isfahan, Hijaz,
# Nahawand, Shiraz, Segah and Rast are all modes before they are destinations here.
#
# Found the hard way. "Isfahan Gazel - Uthman al-Mosuli" was filed under Isfahan, Iran.
# Mulla Uthman al-Mawsili was born in Mosul, died in Baghdad, and cut that cylinder in
# ISTANBUL around 1910-1912. "Isfahan" is the makam he is singing in. The gazetteer had
# placed a Turkish recording of an Iraqi singer in a city none of them had anything to
# do with, and it would have sat on the map looking perfectly plausible.
MODE_NAMES = {"isfahan", "hijaz", "hicaz", "nahawand", "nihavend", "shiraz",
              "segah", "sehgah", "rast", "bayati", "huzzam", "ushaq", "ussak",
              "saba", "kurd", "awj", "awshar"}

# Words that mean "this title is talking about music, not geography".
MODE_CONTEXT = ("gazel", "gazal", "ghazal", "maqam", "makam", "mugham", "muqam",
                "dastgah", "taqsim", "taksim", "pesrev", "peşrev", "semai", "semaisi",
                "sema'i", "tasnif", "tesnif", "sarki", "şarkı", "mode", "in makam")

# name, (aliases...), lat, lng, requires-one-of (for ambiguous names) or None
# Coordinates are city-centre approximations, which is the right precision for a
# recording labelled only with a city name. Claiming more would be false accuracy.
CITIES = [
    # --- Maghreb ---
    ("Fez", ("fes", "fez", "fès", "fes el bali"), 34.0646, -4.9737, None),
    ("Marrakech", ("marrakech", "marrakesh", "marrakesch", "jemaa el fna", "jemaa el-fna"), 31.6295, -7.9811, None),
    ("Casablanca", ("casablanca",), 33.5731, -7.5898, None),
    ("Rabat", ("rabat",), 34.0209, -6.8416, None),
    ("Essaouira", ("essaouira", "mogador"), 31.5085, -9.7595, None),
    ("Tangier", ("tangier", "tanger", "tangiers"), 35.7595, -5.8340, None),
    ("Meknes", ("meknes", "meknès"), 33.8935, -5.5473, None),
    ("Chefchaouen", ("chefchaouen", "chaouen"), 35.1688, -5.2636, None),
    ("Aroumd", ("aroumd", "armed", "imlil"), 31.1361, -7.9192, None),
    ("Algiers", ("algiers", "alger", "algier"), 36.7538, 3.0588, None),
    ("Tlemcen", ("tlemcen",), 34.8783, -1.3150, None),
    ("Constantine", ("constantine",), 36.3650, 6.6147, None),
    ("Tunis", ("tunis",), 36.8065, 10.1815, None),
    ("Kairouan", ("kairouan", "qayrawan"), 35.6781, 10.0963, None),
    ("Sfax", ("sfax",), 34.7406, 10.7603, None),
    ("Tripoli (Libya)", ("tarabulus", "tripoli"), 32.8872, 13.1913, ("libya", "libye", "libyen", "libia")),
    ("Benghazi", ("benghazi",), 32.1167, 20.0667, None),
    ("Nouakchott", ("nouakchott",), 18.0735, -15.9582, None),

    # --- Egypt and Sudan ---
    ("Cairo", ("cairo", "kairo", "le caire", "al qahira", "khan el khalili", "al-azhar", "maadi", "giza"), 30.0444, 31.2357, None),
    ("Alexandria", ("alexandria", "alexandrie", "iskandariya"), 31.2001, 29.9187, None),
    ("Luxor", ("luxor", "louxor"), 25.6872, 32.6396, None),
    ("Aswan", ("aswan",), 24.0889, 32.8998, None),
    ("Port Said", ("port said", "port fouad"), 31.2653, 32.3019, None),
    ("Khartoum", ("khartoum", "khartum"), 15.5007, 32.5599, None),
    ("Omdurman", ("omdurman", "umm durman"), 15.6445, 32.4777, None),

    # --- Levant and Iraq ---
    ("Damascus", ("damascus", "damas", "dimashq"), 33.5138, 36.2765, None),
    ("Aleppo", ("aleppo", "alep", "halab"), 36.2021, 37.1343, None),
    ("Beirut", ("beirut", "beyrouth", "beyrut"), 33.8938, 35.5018, None),
    ("Tripoli (Lebanon)", ("tripoli", "tarablus"), 34.4367, 35.8497, ("lebanon", "liban", "libanon", "lubnan")),
    ("Jerusalem", ("jerusalem", "gerusalemme", "al quds", "al-quds", "hagia"), 31.7683, 35.2137, None),
    ("Ramallah", ("ramallah", "manarah square"), 31.8996, 35.2042, None),
    ("Bethlehem", ("bethlehem", "belem", "nativity church"), 31.7054, 35.2024, None),
    ("Jaffa", ("jaffa", "yafo"), 32.0533, 34.7503, None),
    ("Amman", ("amman",), 31.9454, 35.9284, None),
    ("Aqaba", ("aqaba",), 29.5319, 35.0061, None),
    ("Wadi Rum", ("wadi rum",), 29.5833, 35.4167, None),
    ("Baghdad", ("baghdad", "bagdad"), 33.3152, 44.3661, None),
    ("Mosul", ("mosul", "mawsil", "mosuli", "موصلي"), 36.3350, 43.1189, None),
    ("Basra", ("basra", "basrah"), 30.5085, 47.7804, None),

    # --- Turkey ---
    ("Istanbul", ("istanbul", "estambul", "stamboul", "galata", "sultanahmet", "beyoglu",
                  "beyoğlu", "uskudar", "üsküdar", "eminonu", "fatih", "tarlabasi",
                  "tarlabaşı", "ayvansaray", "kalenderhane", "blue mosque", "istiklal",
                  "golden horn", "bosphorus", "bosporus"), 41.0082, 28.9784, None),
    ("Konya", ("konya",), 37.8746, 32.4932, None),
    ("Bursa", ("bursa", "halilurrahman"), 40.1826, 29.0665, None),
    ("Ankara", ("ankara",), 39.9334, 32.8597, None),
    ("Izmir", ("izmir", "ismir", "smyrna"), 38.4237, 27.1428, None),
    ("Antalya", ("antalya", "kemer", "ulupinar", "ulupınar"), 36.8969, 30.7133, None),
    ("Kas", ("kas", "kaş", "kalkan", "patara"), 36.2020, 29.6383, None),
    ("Gocek", ("gocek", "göcek", "dalyan", "ortaca"), 36.7530, 28.9409, None),
    ("Mardin", ("mardin",), 37.3212, 40.7245, None),
    ("Edirne", ("edirne",), 41.6771, 26.5557, None),

    # --- Iran, Gulf, Arabia ---
    ("Isfahan", ("isfahan", "esfahan", "ispahan", "اصفهان"), 32.6539, 51.6660, None),
    ("Tehran", ("tehran", "teheran"), 35.6892, 51.3890, None),
    ("Shiraz", ("shiraz",), 29.5918, 52.5837, None),
    ("Mashhad", ("mashhad", "meshed"), 36.2605, 59.6168, None),
    ("Yazd", ("yazd",), 31.8974, 54.3569, None),
    ("Mecca", ("mecca", "makkah", "masjid al haram"), 21.4225, 39.8262, None),
    ("Medina (Saudi Arabia)", ("al madinah", "al-madinah", "madinah munawwarah",
                               "prophet's mosque", "prophets mosque"), 24.4672, 39.6111, None),
    ("Jeddah", ("jeddah", "jedda", "jiddah"), 21.4858, 39.1925, None),
    ("Riyadh", ("riyadh", "riyad"), 24.7136, 46.6753, None),
    ("Dubai", ("dubai", "jumeirah"), 25.2048, 55.2708, None),
    ("Abu Dhabi", ("abu dhabi", "abudhabi"), 24.4539, 54.3773, None),
    ("Al Ain", ("al ain",), 24.2075, 55.7447, None),
    ("Doha", ("doha",), 25.2854, 51.5310, None),
    ("Muscat", ("muscat", "masqat"), 23.5880, 58.3829, None),
    ("Wadi Bani Khalid", ("wadi bani khalid",), 22.5667, 59.1500, None),
    ("Sanaa", ("sanaa", "sana'a"), 15.3694, 44.1910, None),

    # --- Caucasus and Central Asia ---
    ("Baku", ("baku", "bakı"), 40.4093, 49.8671, None),
    ("Shusha", ("shusha", "shushi", "şuşa"), 39.7578, 46.7464, None),
    ("Tbilisi", ("tbilisi", "tiflis"), 41.7151, 44.8271, None),
    ("Yerevan", ("yerevan", "erevan"), 40.1792, 44.4991, None),
    ("Makhachkala", ("makhachkala", "махачкала", "dagestan", "дагестан"), 42.9849, 47.5047, None),
    ("Kazan", ("kazan", "казань", "казани"), 55.7961, 49.1064, None),
    ("Bishkek", ("bishkek", "бишкек"), 42.8746, 74.5698, None),
    ("Almaty", ("almaty", "алматы", "turkebaeva"), 43.2220, 76.8512, None),
    ("Tashkent", ("tashkent", "toshkent"), 41.2995, 69.2401, None),
    ("Samarkand", ("samarkand", "samarqand"), 39.6270, 66.9750, None),
    ("Bukhara", ("bukhara", "buxoro"), 39.7747, 64.4286, None),
    ("Kashgar", ("kashgar", "kashi", "kaxgar"), 39.4704, 75.9898, None),
    ("Urumqi", ("urumqi", "ürümqi"), 43.8256, 87.6168, None),
    ("Bakhchysarai", ("bahkchsysaray", "bakhchysarai", "bakhchisaray"), 44.7539, 33.8608, None),

    # --- South Asia ---
    ("Delhi", ("delhi", "dehli", "new delhi", "newdelhi", "nizamuddin"), 28.6139, 77.2090, None),
    ("Lahore", ("lahore",), 31.5204, 74.3587, None),
    ("Karachi", ("karachi",), 24.8607, 67.0011, None),
    ("Islamabad", ("islamabad",), 33.6844, 73.0479, None),
    ("Multan", ("multan",), 30.1575, 71.5249, None),
    ("Ajmer", ("ajmer",), 26.4499, 74.6399, None),
    ("Agra", ("agra", "fatehpur sikri"), 27.1767, 78.0081, None),
    ("Hyderabad (India)", ("hyderabad",), 17.3850, 78.4867, ("india", "telangana")),
    ("Srinagar", ("srinagar",), 34.0837, 74.7973, None),
    ("Dhaka", ("dhaka", "dacca"), 23.8103, 90.4125, None),
    ("Chittagong", ("chittagong", "chattogram"), 22.3569, 91.7832, None),
    ("Bijapur", ("bijapur", "vijayapura", "upli buruz"), 16.8302, 75.7100, None),
    ("Saundatti", ("saundatti",), 15.7667, 75.1167, None),
    ("Leh", ("leh", "ladakh"), 34.1526, 77.5771, None),
    ("Kabul", ("kabul", "darulaman"), 34.5553, 69.2075, None),
    ("Herat", ("herat",), 34.3529, 62.2040, None),

    # --- Southeast Asia ---
    ("Jakarta", ("jakarta", "sagan"), -6.2088, 106.8456, None),
    ("Yogyakarta", ("yogyakarta", "jogja", "merapi"), -7.7956, 110.3695, None),
    ("Bandung", ("bandung",), -6.9175, 107.6191, None),
    ("Surabaya", ("surabaya",), -7.2575, 112.7521, None),
    ("Bali", ("bali", "bedugul", "candikuning", "tabanan"), -8.3405, 115.0920, None),
    ("Lombok", ("lombok", "nusa tenggara"), -8.6500, 116.3242, None),
    ("Ternate", ("ternate",), 0.7900, 127.3800, None),
    ("Kuala Lumpur", ("kuala lumpur", "balakong", "national mosque"), 3.1390, 101.6869, None),
    ("Tanah Rata", ("tanah rata", "cameron highlands"), 4.4700, 101.3800, None),
    ("Koh Bulon", ("koh bulon", "bulon lae"), 7.0333, 99.5500, None),
    ("Male", ("male", "maldives", "bodufolhudhoo"), 4.1755, 73.5093, None),

    # --- Sub-Saharan Africa ---
    ("Dakar", ("dakar",), 14.7167, -17.4677, None),
    ("Saint-Louis", ("saint louis", "st louis"), 16.0179, -16.4896, ("senegal", "sénégal")),
    ("Touba", ("touba",), 14.8500, -15.8833, None),
    ("Bamako", ("bamako",), 12.6392, -8.0029, None),
    ("Djenne", ("djenne", "djenné"), 13.9060, -4.5550, None),
    ("Diafarabe", ("diafarabe", "diafarabé"), 14.1667, -5.0333, None),
    ("Timbuktu", ("timbuktu", "tombouctou"), 16.7735, -3.0074, None),
    ("Kano", ("kano",), 12.0022, 8.5920, None),
    ("Zanzibar", ("zanzibar", "stone town"), -6.1659, 39.2026, None),
    ("Dar es Salaam", ("dar es salaam", "mikocheni"), -6.7924, 39.2083, None),
    ("Mombasa", ("mombasa",), -4.0435, 39.6682, None),
    ("Harar", ("harar",), 9.3110, 42.1180, None),

    # --- Balkans and Europe ---
    ("Sarajevo", ("sarajevo",), 43.8563, 18.4131, None),
    ("Tirana", ("tirana", "kavajes", "kavajës"), 41.3275, 19.8187, None),
    ("Skopje", ("skopje",), 41.9973, 21.4280, None),
    ("Pristina", ("pristina", "prishtina"), 42.6629, 21.1655, None),
    ("Sofia", ("sofia",), 42.6977, 23.3219, None),
    ("Granada", ("granada", "alhambra"), 37.1773, -3.5986, None),
    ("Cordoba", ("cordoba", "córdoba", "mezquita"), 37.8882, -4.7794, None),
    ("Berlin", ("berlin", "friedelstr", "neukölln"), 52.5200, 13.4050, None),
    ("Monchengladbach", ("monchengladbach", "mönchengladbach"), 51.1805, 6.4428, None),
    ("London", ("london", "whitechapel"), 51.5074, -0.1278, None),
    ("Paris", ("paris",), 48.8566, 2.3522, None),
    ("Brussels", ("brussels", "bruxelles", "saint gilles"), 50.8503, 4.3517, None),
    ("Rotterdam", ("rotterdam",), 51.9244, 4.4777, None),

    # --- Americas ---
    ("Hamtramck", ("hamtramck", "holbrook"), 42.3928, -83.0496, None),
    ("Dearborn", ("dearborn",), 42.3223, -83.1763, None),
    ("New York", ("new york", "brooklyn", "queens"), 40.7128, -74.0060, None),
    ("Chicago", ("chicago",), 41.8781, -87.6298, None),
    ("Toronto", ("toronto",), 43.6532, -79.3832, None),
]


# Domain knowledge that no string match can supply. A recording titled
# "Cabbar Qaryagdioglu-Sahnaz.ogg" names a singer, not a place, but the singer is a
# Karabakh mugham master and the tradition belongs to Shusha. Placing it there is a
# claim about the TRADITION, not about where the microphone stood, so it is recorded
# with a different basis and should be labelled differently in the UI.
COLLECTIONS = [
    (("cabbar qaryagdioglu", "jabbar garyagdioglu", "jabbar karyagdi", "jabbar garyagdy",
      "qaryagdioglu", "garyagdioglu"), "Shusha", 39.7578, 46.7464,
     "Karabakh mugham, Jabbar Garyagdioglu, recorded 1906-1912"),
    (("husseyni saz semayissi",), "Istanbul", 41.0082, 28.9784,
     "Ottoman saz semaisi"),
    (("uthman al-mosuli", "uthman al-musili", "al-mawsili", "الموصلي", "mosuli"),
     "Istanbul", 41.0082, 28.9784,
     "Mulla Uthman al-Mawsili of Mosul (1854-1923), recorded on cylinder in Istanbul "
     "around 1910-1912; 'Isfahan' in the title is the makam, not the city"),
]


def find_collection(title: str):
    """Match a known performer or collection whose place is known from scholarship."""
    haystack = normalize_text(title)
    for aliases, place, lat, lng, note in COLLECTIONS:
        for alias in aliases:
            if normalize_text(alias) in haystack:
                return place, lat, lng, note
    return None


def build_index() -> list[tuple[str, str, float, float, tuple]]:
    """
    Flatten the city list into (alias, city, lat, lng, requires), longest alias first.

    Longest first matters: "new delhi" must be tested before "delhi", and
    "tripoli lebanon" before "tripoli", or the shorter name wins and the
    more specific information is thrown away.
    """
    index = []
    for city, aliases, lat, lng, requires in CITIES:
        for alias in aliases:
            if normalize_text(alias) in NEVER_A_PLACE:
                continue
            index.append((normalize_text(alias), city, lat, lng, requires))
    return sorted(index, key=lambda row: -len(row[0]))


INDEX = build_index()


def find_place(title: str):
    """
    Return (city, lat, lng, matched_alias) for the first confident match, or None.

    Confident means: the alias appears as whole words, and if the alias is
    ambiguous (Tripoli is in both Libya and Lebanon) a disambiguating word is
    present too. An ambiguous name with no disambiguator returns None. Refusing
    to answer is a valid answer.
    """
    haystack = normalize_text(title)
    # If the title is clearly about music, a mode name in it is a mode, not a place.
    musical = any(word in haystack for word in MODE_CONTEXT)
    for alias, city, lat, lng, requires in INDEX:
        if not re.search(rf"\b{re.escape(alias)}\b", haystack):
            continue
        if musical and alias in MODE_NAMES:
            continue          # "Isfahan Gazel" is a mode and a song, not a destination
        if requires and not any(re.search(rf"\b{re.escape(normalize_text(word))}\b", haystack)
                                for word in requires):
            continue          # ambiguous name, no country hint: decline to guess
        return city, lat, lng, alias
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Add coordinates from place names in titles.")
    parser.add_argument("--apply", action="store_true",
                        help="write the coordinates into sawt_candidates.json (default: dry run)")
    args = parser.parse_args()

    if not CANDIDATES.exists():
        raise SystemExit(f"No results at {CANDIDATES}. Run sawt_harvester.py first.")
    items = json.loads(CANDIDATES.read_text(encoding="utf-8"))

    missing = [c for c in items if c.get("lat") is None or c.get("lng") is None]
    print(f"{len(missing)} of {len(items)} candidates have no coordinates.\n")

    matched, by_city = [], Counter()
    for c in missing:
        collection = find_collection(c["title"])
        if collection:
            place, lat, lng, note = collection
            matched.append((c, place, lat, lng, note, "tradition"))
            by_city[f"{place} (tradition)"] += 1
            continue
        hit = find_place(c["title"])
        if hit:
            city, lat, lng, alias = hit
            matched.append((c, city, lat, lng, alias, "title"))
            by_city[city] += 1

    print(f"Place name found in the title for {len(matched)} of them:\n")
    for city, n in by_city.most_common():
        print(f"  {n:>4}  {city}")

    print("\nSample of what would be placed:")
    for c, city, lat, lng, alias, basis in matched[:15]:
        print(f"  [{basis:<9}] {city:<20} <- \"{c['title'][:52]}\"")

    if not args.apply:
        print(f"\nDry run. Nothing written. Re-run with --apply to add these "
              f"{len(matched)} coordinates.")
        return

    for c, city, lat, lng, alias, basis in matched:
        c["lat"], c["lng"] = lat, lng
        # Record how the coordinate was obtained, so it is auditable and reversible.
        # A geotag, a filename guess and a claim about a tradition are three different
        # kinds of fact, and the map should not present them as if they were one.
        c["place_basis"] = basis
        c["geocoded_from"] = f"{basis}: {alias} -> {city}"
        if basis == "tradition":
            c.setdefault("notes", []).append(
                f"Placed at {city} on the basis of the tradition ({alias}), not the "
                f"recording location, which is unknown. Label accordingly.")
        else:
            c.setdefault("notes", []).append(
                f"Coordinates inferred from the title (\"{alias}\"), city centre of {city}. "
                f"Not a geotag. Verify before publishing.")
    CANDIDATES.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    placed = sum(1 for c in items if c.get("lat") is not None)
    print(f"\nWrote {len(matched)} coordinates. {placed} of {len(items)} candidates now placeable.")


if __name__ == "__main__":
    main()


# ------------------------------------------------------------------
# Reverse lookup: coordinates back to a human place name
# ------------------------------------------------------------------
#
# The gazetteer already knows where ~140 cities are. Reading it backwards turns a
# bare pair of numbers into "near Marrakech, Morocco", which is what a listener
# actually wants to be told. This is offline reverse geocoding: crude compared to a
# real service, but it needs no network, no API key, and no rate limit, and its
# errors are obvious rather than subtle.

CITY_COUNTRY = {
    "Fez": "Morocco", "Marrakech": "Morocco", "Casablanca": "Morocco", "Rabat": "Morocco",
    "Essaouira": "Morocco", "Tangier": "Morocco", "Meknes": "Morocco",
    "Chefchaouen": "Morocco", "Aroumd": "Morocco",
    "Algiers": "Algeria", "Tlemcen": "Algeria", "Constantine": "Algeria",
    "Tunis": "Tunisia", "Kairouan": "Tunisia", "Sfax": "Tunisia",
    "Tripoli (Libya)": "Libya", "Benghazi": "Libya", "Nouakchott": "Mauritania",
    "Cairo": "Egypt", "Alexandria": "Egypt", "Luxor": "Egypt", "Aswan": "Egypt",
    "Port Said": "Egypt", "Khartoum": "Sudan", "Omdurman": "Sudan",
    "Damascus": "Syria", "Aleppo": "Syria", "Beirut": "Lebanon",
    "Tripoli (Lebanon)": "Lebanon", "Jerusalem": "Jerusalem",
    "Ramallah": "Palestine", "Bethlehem": "Palestine", "Jaffa": "Israel",
    "Amman": "Jordan", "Aqaba": "Jordan", "Wadi Rum": "Jordan",
    "Baghdad": "Iraq", "Mosul": "Iraq", "Basra": "Iraq",
    "Istanbul": "Turkey", "Konya": "Turkey", "Bursa": "Turkey", "Ankara": "Turkey",
    "Izmir": "Turkey", "Antalya": "Turkey", "Kas": "Turkey", "Gocek": "Turkey",
    "Mardin": "Turkey", "Edirne": "Turkey",
    "Isfahan": "Iran", "Tehran": "Iran", "Shiraz": "Iran", "Mashhad": "Iran", "Yazd": "Iran",
    "Mecca": "Saudi Arabia", "Medina (Saudi Arabia)": "Saudi Arabia",
    "Jeddah": "Saudi Arabia", "Riyadh": "Saudi Arabia",
    "Dubai": "United Arab Emirates", "Abu Dhabi": "United Arab Emirates",
    "Al Ain": "United Arab Emirates", "Doha": "Qatar",
    "Muscat": "Oman", "Wadi Bani Khalid": "Oman", "Sanaa": "Yemen",
    "Baku": "Azerbaijan", "Shusha": "Karabakh", "Tbilisi": "Georgia", "Yerevan": "Armenia",
    "Makhachkala": "Dagestan, Russia", "Kazan": "Tatarstan, Russia",
    "Bishkek": "Kyrgyzstan", "Almaty": "Kazakhstan",
    "Tashkent": "Uzbekistan", "Samarkand": "Uzbekistan", "Bukhara": "Uzbekistan",
    "Kashgar": "Xinjiang, China", "Urumqi": "Xinjiang, China", "Bakhchysarai": "Crimea",
    "Delhi": "India", "Agra": "India", "Ajmer": "India", "Hyderabad (India)": "India",
    "Srinagar": "Kashmir", "Bijapur": "India", "Saundatti": "India", "Leh": "India",
    "Lahore": "Pakistan", "Karachi": "Pakistan", "Islamabad": "Pakistan", "Multan": "Pakistan",
    "Dhaka": "Bangladesh", "Chittagong": "Bangladesh",
    "Kabul": "Afghanistan", "Herat": "Afghanistan",
    "Jakarta": "Indonesia", "Yogyakarta": "Indonesia", "Bandung": "Indonesia",
    "Surabaya": "Indonesia", "Bali": "Indonesia", "Lombok": "Indonesia", "Ternate": "Indonesia",
    "Kuala Lumpur": "Malaysia", "Tanah Rata": "Malaysia", "Koh Bulon": "Thailand",
    "Male": "Maldives",
    "Dakar": "Senegal", "Saint-Louis": "Senegal", "Touba": "Senegal",
    "Bamako": "Mali", "Djenne": "Mali", "Diafarabe": "Mali", "Timbuktu": "Mali",
    "Kano": "Nigeria", "Zanzibar": "Tanzania", "Dar es Salaam": "Tanzania",
    "Mombasa": "Kenya", "Harar": "Ethiopia",
    "Sarajevo": "Bosnia", "Tirana": "Albania", "Skopje": "North Macedonia",
    "Pristina": "Kosovo", "Sofia": "Bulgaria",
    "Granada": "Spain", "Cordoba": "Spain",
    "Berlin": "Germany", "Monchengladbach": "Germany", "London": "United Kingdom",
    "Paris": "France", "Brussels": "Belgium", "Rotterdam": "Netherlands",
    "Hamtramck": "Michigan, USA", "Dearborn": "Michigan, USA",
    "New York": "USA", "Chicago": "USA", "Toronto": "Canada",
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres. The Earth is a sphere, so Pythagoras lies."""
    import math
    radius = 6371.0
    rad = math.radians
    a = (math.sin(rad(lat2 - lat1) / 2) ** 2
         + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(rad(lng2 - lng1) / 2) ** 2)
    return 2 * radius * math.asin(math.sqrt(a))


def nearest_place(lat: float, lng: float, limit_km: float = 250.0):
    """
    Nearest known city, or None if nothing is close enough to be worth naming.

    The limit matters. Without it, a recording in the middle of the Sahara would be
    labelled "Timbuktu" from 900km away, which is worse than saying nothing.
    """
    best, best_km = None, None
    for city, _aliases, city_lat, city_lng, _requires in CITIES:
        distance = haversine_km(lat, lng, city_lat, city_lng)
        if best_km is None or distance < best_km:
            best, best_km = city, distance
    if best is None or best_km > limit_km:
        return None
    country = CITY_COUNTRY.get(best, "")
    # Strip the disambiguating suffix we needed internally: "Tripoli (Libya)" reads
    # better to a listener as "Tripoli, Libya".
    display = re.sub(r"\s*\([^)]*\)$", "", best)
    return {"city": display, "country": country, "km": round(best_km)}
