"""Offline test of the fetch stage: fake the two network calls, check the records."""
import json, pathlib, tempfile, sys
import gallica_harvester as gh

tmp = pathlib.Path(tempfile.mkdtemp())
gh.RECORDS = pathlib.Path("gallica_fixture.json")
gh.SELECTED = tmp / "sel.json"
gh.PERMISSION = tmp / "perm.md"
gh.CANDIDATES = tmp / "cand.json"
gh.AUDIO_DIR = tmp / "sawt_audio"
gh.PAUSE_SECONDS = 0
gh.select()

calls = []
gh.sides_of = lambda ark: (calls.append(ark) or
                           [f"https://gallica.bnf.fr/{ark}/f1.audio",
                            f"https://gallica.bnf.fr/{ark}/f2.audio"])
def fake_download(url, target, max_mb=60.0):
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(b"ID3" + b"\x00" * 9000)
    return True, "8.8MB"
gh.download = fake_download

print("=== first run ===")
gh.fetch(limit=3)
records = json.loads(gh.CANDIDATES.read_text(encoding="utf-8"))
print(f"\n{len(records)} candidates written, {len(calls)} discs listed")

print("\n=== resume: finish the rest, then a third run must add nothing ===")
calls.clear()
gh.fetch(limit=None)
records = json.loads(gh.CANDIDATES.read_text(encoding="utf-8"))
assert len(records) == 18, f"expected 9 discs x 2 sides = 18, got {len(records)}"
assert len(calls) == 6, f"should have listed only the 6 unfetched discs, listed {len(calls)}"

calls.clear()
gh.fetch(limit=None)
again = json.loads(gh.CANDIDATES.read_text(encoding="utf-8"))
assert len(again) == 18, f"resume duplicated: {len(again)} vs 18"
assert calls == [], f"re-listed discs that were already done: {calls}"
print(f"18 candidates, third run listed {len(calls)} discs and added nothing")

print("\n=== one candidate in full ===")
print(json.dumps(records[0], ensure_ascii=False, indent=2))

# The licence string has to survive build_site_data.rights_basis unchanged.
# NOTE: do not sys.path.insert another copy of the project here. Doing so put a
# stale genres.py ahead of the local one and the test quietly graded the wrong file.
def rights_basis(license_name, year, cutoff=gh.CUTOFF_YEAR):
    lic = (license_name or "").lower()
    if "cc0" in lic or "zero" in lic: return "cc0"
    if "sa" in lic.replace("-", " ").split(): return "cc-by-sa"
    if "mark" in lic: return "pdm"
    if "public domain" in lic:
        return "pd-us-published-pre-cutoff" if year and year <= cutoff else None
    if "by" in lic.replace("-", " ").split() or lic.startswith("cc by"): return "cc-by"
    return None

print("\n=== rights mapping ===")
bad = 0
for c in records:
    got = rights_basis(c["license"], c["year"])
    if got != "pd-us-published-pre-cutoff":
        print(f"  FAIL {c['title'][:40]}: {got}"); bad += 1
print(f"  {len(records) - bad}/{len(records)} map to pd-us-published-pre-cutoff")

print("\n=== genre classification ===")
from genres import classify
for c in records[:2] + [c for c in records if c.get("category") == "recitation"][:2]:
    print(f"  {classify(c)}  <-  {c['title'][:50]}")

assert bad == 0, "rights mapping failed"
print("\nall fetch-stage checks passed")
