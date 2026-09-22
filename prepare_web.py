"""
prepare_web.py
Copy the validated data and its audio into the Next.js app, rewriting paths for the web.

Two different worlds, two different kinds of path:

    site/tracks.json   audioUrl "sawt_web/171928.opus"   a path on your disk
    web/public/...     audioUrl "audio/171928.opus"      a path on a web server

Next serves anything in public/ from the site root, so public/audio/171928.opus is
reachable at /audio/171928.opus and nothing else is reachable at all. That is why the
files have to be copied rather than pointed at: a web server will not follow a path
out of the folder it was told to serve, and you would not want one that did.

Only the audio actually referenced by a track is copied. Rejected recordings stay
where they are.

Run:  python prepare_web.py
"""

import json
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SITE = SCRIPT_DIR / "site"
WEB_PUBLIC = SCRIPT_DIR / "web" / "public"


def main() -> None:
    tracks = json.loads((SITE / "tracks.json").read_text(encoding="utf-8"))
    hubs = json.loads((SITE / "hubs.json").read_text(encoding="utf-8"))

    (WEB_PUBLIC / "data").mkdir(parents=True, exist_ok=True)
    (WEB_PUBLIC / "audio").mkdir(parents=True, exist_ok=True)

    copied = missing = skipped = 0
    total_mb = 0.0
    for track in tracks:
        source = SCRIPT_DIR / track["audioUrl"].replace("\\", "/")
        name = source.name
        target = WEB_PUBLIC / "audio" / name
        if not source.exists():
            missing += 1
            print(f"  MISSING {source}")
            continue
        if target.exists() and target.stat().st_size == source.stat().st_size:
            skipped += 1
        else:
            shutil.copy2(source, target)
            copied += 1
        total_mb += target.stat().st_size / 1_048_576
        track["audioUrl"] = f"audio/{name}"
        # The master never goes near the web build. Keep the reference for provenance,
        # tidied of Windows backslashes, but do not copy the file.
        if track.get("archivalUrl"):
            track["archivalUrl"] = track["archivalUrl"].replace("\\", "/")

    # Prune what no track names any more.
    #
    # Copying is not enough on its own. A track that gets rejected, quarantined or
    # re-encoded leaves its old file sitting in public/, where Next will happily
    # export it and a web server will happily serve it to anyone who guesses the
    # name. For a superseded encode that is wasted bytes. For the four recordings
    # just held back as Quran recitation it is the quarantine leaking, which is
    # worse, and it would have leaked silently.
    #
    # public/audio is a build output, not a store. Everything here is reproducible
    # from sawt_web, so deleting is safe in a way that deleting from sawt_web is not.
    wanted = {Path(t["audioUrl"]).name for t in tracks}
    pruned = pruned_mb = 0
    for existing in (WEB_PUBLIC / "audio").iterdir():
        if existing.is_file() and existing.name not in wanted:
            pruned_mb += existing.stat().st_size / 1_048_576
            existing.unlink()
            pruned += 1

    (WEB_PUBLIC / "data" / "tracks.json").write_text(
        json.dumps(tracks, ensure_ascii=False, indent=2), encoding="utf-8")
    (WEB_PUBLIC / "data" / "hubs.json").write_text(
        json.dumps(hubs, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(tracks)} tracks, {len(hubs)} hubs written to web/public/data/")
    print(f"audio: {copied} copied, {skipped} already current, {missing} missing, "
          f"{pruned} pruned ({total_mb:.0f} MB in web/public/audio/)")
    if pruned:
        print(f"  pruned {pruned_mb:.0f} MB no longer named by any track")
    if missing:
        print("\nA missing file means a track points at audio that is not on disk.")
        print("Re-run make_web_audio.py, then build_site_data.py --write, then this.")


if __name__ == "__main__":
    main()
