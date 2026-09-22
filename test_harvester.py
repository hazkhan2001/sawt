"""Offline test of fetch_freesound paging. No network: requests.get is replaced by a fake."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import requests
import sawt_harvester as sh

calls = []

# fetch_freesound now takes a search dict, not a bare string.
ADHAN = {"query": "adhan", "accept": ["adhan"], "match": sh.MATCH_PREFIX}
NOTHING = {"query": "nothing", "accept": ["nothing"], "match": sh.MATCH_PREFIX}

def make_result(n):
    return {"id": n, "name": f"adhan sound {n}", "license": "http://creativecommons.org/publicdomain/zero/1.0/",
            "username": "tester", "url": f"https://freesound.org/people/tester/sounds/{n}/",
            "geotag": "41.008 28.978" if n % 2 == 0 else None,
            "previews": {"preview-hq-mp3": f"https://cdn/{n}.mp3"}, "duration": 12.5}

class FakeResponse:
    """Stands in for a requests Response. get_json now inspects the status and
    headers before parsing, so the fake has to provide those too."""
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.reason = "OK"
        self.headers = {"Content-Type": "application/json"}
        self.url = "https://fake.test/"
        self.text = "{}"
    def json(self): return self.payload

def fake_get(url, params=None, headers=None, timeout=None):
    calls.append((url, params))
    page = len(calls)
    if page < 3:
        return FakeResponse({"count": 350, "next": f"https://freesound.org/apiv2/search/text/?page={page+1}&token=X",
                             "results": [make_result(page * 100 + i) for i in range(3)]})
    return FakeResponse({"count": 350, "next": None, "results": [make_result(999)]})

requests.get = fake_get
sh.time.sleep = lambda s: None

out = sh.fetch_freesound(ADHAN, "FAKE_TOKEN")

print("TEST 1: follows next until null")
print("  pages requested:", len(calls))
print("  candidates returned:", len(out))
assert len(calls) == 3, calls
assert len(out) == 7, len(out)
print("  first request sent params:", calls[0][1] is not None)
print("  second request sent params:", calls[1][1] is not None)
assert calls[0][1] is not None and calls[1][1] is None
print("  geotag parsed:", out[0].lat, out[0].lng, "| no geotag:", out[1].lat)
assert out[0].lat == 41.008 and out[1].lat is None
assert out[0].license == "CC0" and out[0].source == "freesound"
print("  PASS")

print("TEST 2: max_pages safety belt")
calls.clear()
def always_next(url, params=None, headers=None, timeout=None):
    calls.append((url, params))
    return FakeResponse({"count": 9999, "next": "https://freesound.org/apiv2/search/text/?page=99&token=X",
                         "results": [make_result(1)]})
requests.get = always_next
out2 = sh.fetch_freesound(ADHAN, "FAKE_TOKEN", max_pages=4)
print("  pages requested:", len(calls), "candidates:", len(out2))
assert len(calls) == 4 and len(out2) == 4
print("  PASS")

print("TEST 3: auth error stops cleanly")
calls.clear()
def refuse(url, params=None, headers=None, timeout=None):
    calls.append((url, params))
    return FakeResponse({"detail": "Invalid token."})
requests.get = refuse
out3 = sh.fetch_freesound(ADHAN, "BAD")
print("  pages requested:", len(calls), "candidates:", len(out3))
assert len(calls) == 1 and out3 == []
print("  PASS")

print("TEST 4: empty last page")
calls.clear()
def one_page(url, params=None, headers=None, timeout=None):
    calls.append((url, params))
    return FakeResponse({"count": 0, "next": None, "results": []})
requests.get = one_page
assert sh.fetch_freesound(NOTHING, "X") == []
print("  PASS")




# ------------------------------------------------------------------
# Multi-script relevance tests
# ------------------------------------------------------------------
print("\nTEST 5: normalisation flattens spelling variants")
assert sh.normalize_text("أَذَان") == sh.normalize_text("اذان"), sh.normalize_text("أَذَان")
assert sh.normalize_text("ذکر") == sh.normalize_text("ذكر")        # Persian kaf vs Arabic kaf
assert sh.normalize_text("صوفی") == sh.normalize_text("صوفي")      # Persian yeh vs Arabic yeh
assert sh.normalize_text("EZAN") == "ezan"
print("  PASS")

print("TEST 6: match modes behave differently, on purpose")
by_query = {s["query"]: s for s in sh.FREESOUND_SEARCHES}

cases = [
    # (sound name, tags, which search, expected)
    ("Oude Haven live 100309.WAV", [], "oud", False),      # WORD rejects the Dutch stem
    ("oud taqsim.wav", [], "oud", True),
    ("Sabah ezani Istanbul", [], "ezan", True),            # PREFIX allows the Turkish suffix
    ("ezan", [], "ezan", True),
    ("Mezanine lift", [], "ezan", False),                  # PREFIX still needs a word start
    ("Утренний азана в Казани", [], "азан", True),         # PREFIX allows the Russian ending
    ("الأذان من الجامع الأزهر", [], "أذان", True),          # LOOSE gets past the attached al-
    ("أَذَان الفجر", [], "أذان", True),                      # diacritics do not block it
    ("ذکر نقشبندی", [], "ذكر", True),                       # Persian kaf matches Arabic kaf
    ("Blue Mosque Istanbul", ["mosque", "istanbul"], "masjid", True),   # tag hit, not title
    ("boogie woogie fun", [], "duduk", False),
    ("Surah Al-Fatiha tilawah", [], "tilawa", True),
]

bad = 0
for name, tags, query, expected in cases:
    got = sh.looks_relevant({"name": name, "tags": tags}, by_query[query])
    if got != expected:
        bad += 1
        print(f"  FAIL {query!r} vs {name!r}: got {got}, wanted {expected}")
assert bad == 0, f"{bad} relevance failures"
print(f"  {len(cases)} cases, all correct")
print("  PASS")

print("TEST 7: recitation searches are marked for quarantine")
recitation = [s for s in sh.FREESOUND_SEARCHES if s.get("category") == "recitation"]
assert len(recitation) >= 4, len(recitation)
c = sh.freesound_to_candidate(
    {"name": "Quran recitation", "tags": [], "license": "http://creativecommons.org/publicdomain/zero/1.0/",
     "username": "x", "url": "https://freesound.org/people/x/sounds/1/", "previews": {}, "duration": 1.0},
    by_query["quran"])
assert c.category == "recitation" and c.found_by == "quran"
print(f"  {len(recitation)} recitation searches, all carrying category=recitation")
print("  PASS")

print("TEST 8: every search is well formed")
for s in sh.FREESOUND_SEARCHES:
    assert s["query"] and s["accept"], s
    assert s.get("match", sh.MATCH_WORD) in (sh.MATCH_WORD, sh.MATCH_PREFIX, sh.MATCH_LOOSE), s
    # A search must accept its own query, or it can never keep anything it finds.
    if s["match"] != sh.MATCH_LOOSE or True:
        assert sh.looks_relevant({"name": s["query"], "tags": []}, s), f"self-check failed: {s['query']}"
print(f"  {len(sh.FREESOUND_SEARCHES)} searches, all valid and self-consistent")
print("  PASS")




print("\nTEST 9: separator normalisation")
assert sh.normalize_text("Call_To_Prayer_Loud_Fes") == "call to prayer loud fes"
assert sh.normalize_text("ezan-distant.aif") == "ezan distant aif"
assert sh.normalize_text("a   b\t c") == "a b c"
assert sh.looks_relevant({"name": "oud_taqsim.wav", "tags": []}, by_query["oud"])
assert not sh.looks_relevant({"name": "Oude Haven.wav", "tags": []}, by_query["oud"])
print("  PASS")

print("TEST 10: Commons search parsing and filtering")
def commons_page(title, mediatype="AUDIO", lic="CC0"):
    return {"title": f"File:{title}",
            "imageinfo": [{"mediatype": mediatype, "mime": "audio/ogg",
                           "url": f"https://upload.wikimedia.org/{title}",
                           "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{title}",
                           "extmetadata": {"LicenseShortName": {"value": lic},
                                           "DateTimeOriginal": {"value": "1912"}}}]}

fake_commons = {"query": {"pages": {
    "1": commons_page("Azan_from_Medina.ogg"),
    "2": commons_page("Cabbar_Qaryagdioglu-Mahur.ogg"),
    "3": commons_page("Photo_of_a_mosque.jpg", mediatype="BITMAP"),
    "4": commons_page("Unrelated_birdsong.ogg"),
}}}
requests.get = lambda url, params=None, headers=None, timeout=None: FakeResponse(fake_commons)
out = sh.fetch_commons_search(by_query["adhan"])
names = [c.title for c in out]
assert names == ["Azan_from_Medina.ogg"], names       # image skipped, birdsong filtered out
assert out[0].year == 1912 and out[0].license == "CC0"
assert out[0].found_by == "adhan" and out[0].source == "commons"
print("  kept only the relevant audio file, parsed year and license")
print("  PASS")



print("\nTEST 11: get_json turns junk responses into readable errors")
import requests as _rq

def html_error(url, params=None, headers=None, timeout=None):
    r = FakeResponse({}, status=200)
    r.headers = {"Content-Type": "text/html"}
    r.text = "<!DOCTYPE html><html><head><title>429 Too Many Requests</title>"
    def boom(): raise ValueError("Expecting value: line 1 column 1 (char 0)")
    r.json = boom
    return r

sh.requests.get = html_error
try:
    sh.get_json("https://commons.wikimedia.org/w/api.php", attempts=1)
    raise AssertionError("should have raised")
except _rq.RequestException as err:
    assert "text/html" in str(err) and "429" in str(err), str(err)
    print(f"  {str(err)[:78]}")

def status_500(url, params=None, headers=None, timeout=None):
    return FakeResponse({}, status=503)
sh.requests.get = status_500
sh.time.sleep = lambda s: None
try:
    sh.get_json("https://example.test/", attempts=2)
    raise AssertionError("should have raised")
except _rq.RequestException as err:
    assert "503" in str(err), str(err)
    print(f"  {str(err)[:78]}")
print("  PASS")

print("TEST 12: Commons coordinates are read off the page")
page = {"title": "File:Azan_Medina.ogg",
        "coordinates": [{"lat": 24.4672, "lon": 39.6111, "type": "landmark"}],
        "imageinfo": [{"mediatype": "AUDIO", "mime": "audio/ogg",
                       "url": "https://upload.wikimedia.org/x.ogg",
                       "descriptionurl": "https://commons.wikimedia.org/wiki/File:Azan_Medina.ogg",
                       "extmetadata": {"LicenseShortName": {"value": "CC0"}}}]}
c = sh.commons_page_to_candidate(page, by_query["adhan"])
assert (c.lat, c.lng) == (24.4672, 39.6111), (c.lat, c.lng)
no_coords = sh.commons_page_to_candidate(
    {"title": "File:x.ogg", "imageinfo": page["imageinfo"]}, by_query["adhan"])
assert no_coords.lat is None            # a file with no {{Location}} must not crash
print(f"  Medina at {c.lat}, {c.lng}; missing coordinates handled")
print("  PASS")



import tempfile, json as _json
print("\nTEST 13: checkpoints save everything, not just the pending subset")

done = sh.Candidate("commons", "already done", "https://x/1", "CC0")
done.playable, done.audio_url = True, "https://x/1.ogg"
todo = sh.Candidate("commons", "still to do", "https://x/2", "CC0")
todo.audio_url = "https://x/2.ogg"
everything = [done, todo]

sh.requests.get = lambda url, params=None, headers=None, timeout=None: FakeResponse({})
sh.check_playable = lambda url, attempts=3: (True, "200 audio/ogg")
sh.time.sleep = lambda s: None

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "out.json"
    # every=1 forces a checkpoint after the single pending item
    sh.resolve_all([todo], None, checkpoint_path=path, checkpoint_list=everything, every=1)
    saved = _json.loads(path.read_text(encoding="utf-8"))
    titles = [s["title"] for s in saved]
    assert titles == ["already done", "still to do"], titles
    assert all(s["playable"] for s in saved)
print("  checkpoint kept the already-resolved item instead of dropping it")
print("  PASS")



print("\nTEST 14: pronunciation-clip filter, including the Arabic al-/el- trap")
for title, want in [
    ("LL-Q150 (fra)-VictorDtmtc-adhan.wav", True),
    ("De-Muezzin.ogg", True),
    ("Nl-oud-ministers.ogg", True),          # Dutch "oud-" compounds, 40+ of them
    ("En-us-mosque.ogg", True),
    ("Fr-Paris--qasida.ogg", True),
    ("At-Tuweisa, Jordan - Adhan from nearby mosque", False),   # real place, not a lang code
    ("El-Hussein Mosque, El-Gamaleya", False),                  # real place
    ("Al-Fatiha recitation.ogg", False),
    ("Cabbar Qaryagdioglu-Sahnaz.ogg", False),
    ("Beautiful adhan.ogg", False),
]:
    got = sh.is_pronunciation_clip(title)
    assert got == want, f"{title!r}: got {got}, wanted {want}"
print("  10 cases, including 4 that an earlier looser pattern got wrong")
print("  PASS")



print("\nTEST 15: genre classification")
from genres import classify, fold

assert fold("bağlama") == "baglama"
assert fold("Dəşti təsnifi") == "desti tesnifi"      # Azeri schwa has no NFKD form
assert fold("müezzin") == "muezzin"

for title, want_genre in [
    ("Isha adhan, Sultanahmet, Istanbul", "adhan"),
    ("Istanbul, mosqué bleue. Appel à la prière", "adhan"),   # French label
    ("Naqshbandi zikr 'Asiklar', Bursa", "dhikr_hadra"),
    ("Sufi zikr song Nakshibandi Islamic -Naat", "dhikr_hadra"),  # dhikr wins over naat
    ("Cabbar Qaryağdıoğlu-Dəşti təsnifi.ogg", "art_music"),
    ("Yavuz-Akalin-Ney.wav", "instrument"),
    ("Surah Al-Fatiha tilawah", "tilawa"),
    ("Marrakech, La Koutubia Mosque", "ambience"),
    ("Koh Bulon Lae, Thailand - drone log", "other"),
]:
    got = classify({"title": title})[0]
    assert got == want_genre, f"{title!r}: got {got}, wanted {want_genre}"

# The quarantine flag must beat any title guess: it is a decision, not an inference.
assert classify({"title": "oud taqsim", "category": "recitation"})[0] == "tilawa"
print("  9 titles plus the quarantine override, all correct")
print("  PASS")



print("\nTEST 16: OAuth2 token expiry is stored as an absolute time")
import freesound_download as fd
import tempfile, time as _time

with tempfile.TemporaryDirectory() as tmp:
    fd.TOKEN_PATH = Path(tmp) / "tok.json"
    fd.save_tokens({"access_token": "abc", "refresh_token": "xyz", "expires_in": 86400})
    saved = _json.loads(fd.TOKEN_PATH.read_text())
    # "expires_in: 86400" is useless tomorrow; "expires_at" is a fact that stays true.
    assert "expires_at" in saved
    assert abs(saved["expires_at"] - (_time.time() + 86400)) < 5
    assert fd.access_token() == "abc"          # still valid, no refresh needed

    # A token that expires inside the safety margin must NOT be handed out as valid.
    fd.save_tokens({"access_token": "old", "refresh_token": "xyz", "expires_in": 30})
    called = {"n": 0}
    def fake_post(url, headers=None, timeout=None, data=None):
        called["n"] += 1
        r = FakeResponse({"access_token": "fresh", "refresh_token": "xyz", "expires_in": 86400})
        return r
    fd.requests.post = fake_post
    fd.load_secret = lambda name: "dummy"
    assert fd.access_token() == "fresh", "expiring token should trigger a refresh"
    assert called["n"] == 1
print("  absolute expiry stored, refresh fires inside the safety margin")
print("  PASS")

print("TEST 17: sound id parsing")
assert fd.sound_id("https://freesound.org/people/nesibe/sounds/171928/") == "171928"
assert fd.sound_id("https://freesound.org/people/x/sounds/1/") == "1"
assert fd.sound_id("https://commons.wikimedia.org/wiki/File:x.ogg") is None
assert fd.sound_id("") is None
print("  PASS")



print("\nTEST 18: a throttled download is retried, not skipped")
import types
calls = []
def flaky(sid, token, destination, max_mb):
    calls.append(sid)
    # First attempt on sound 2 is throttled; the retry succeeds.
    if sid == "2" and calls.count("2") == 1:
        return False, "429 rate limited: throttled"
    return True, f"{sid}.mp3 (1.0MB)"
fd.download = flaky
fd.time.sleep = lambda s: None
fd.access_token = lambda: "tok"
fd.AUDIO_DIR = Path(tempfile.mkdtemp())
fd.CANDIDATES = Path(tempfile.mkdtemp()) / "c.json"
fd.CANDIDATES.write_text(_json.dumps([
    {"source": "freesound", "tier": "A", "lat": 1, "lng": 1,
     "page_url": f"https://freesound.org/people/x/sounds/{i}/", "title": f"s{i}"}
    for i in (1, 2, 3)]), encoding="utf-8")
fd.sys = sys
sys.argv = ["freesound_download.py"]
fd.main()
assert calls == ["1", "2", "2", "3"], calls
print(f"  call order {calls}: sound 2 was retried in place, 3 still ran")
print("  PASS")

print("\nAll tests passed.")
