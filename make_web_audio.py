"""
make_web_audio.py
Turn the archival originals into files a browser can actually stream.

Two files per recording, on purpose, because they do different jobs:

  sawt_audio/   the original as the recordist made it. A 258MB 24-bit WAV is not a
                mistake, it is the master. Keep it, never serve it.
  sawt_web/     a small mono file for the map. Around 1MB for a three minute adhan.

Your data model already knows about this split: SoundTrack.audioUrl is the streaming
copy, and the harvester has carried an archival_url all along.

Why mono, and why 96kbps: these are field recordings of a voice carrying across a
city, not studio music. Stereo doubles the bytes to preserve a stereo image that a
phone speaker will collapse anyway, and past about 96kbps for speech you are
spending bandwidth on noise floor.

Run:  python make_web_audio.py
      python make_web_audio.py --format mp3     (if Opus support matters less than reach)
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from config import keep_awake

SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = SCRIPT_DIR / "sawt_audio"
WEB_DIR = SCRIPT_DIR / "sawt_web"
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"


def find_ffmpeg() -> str:
    """
    Locate ffmpeg, preferring one already on the system.

    shutil.which searches PATH the same way the shell does. If that fails, the
    imageio-ffmpeg package ships a working static build, which is the least painful
    way to get ffmpeg on Windows without an installer or a PATH edit.
    """
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit(
            "ffmpeg not found. Either install it:\n"
            "    winget install Gyan.FFmpeg\n"
            "or get a bundled copy with no installer:\n"
            "    pip install imageio-ffmpeg")


def encode(ffmpeg: str, source: Path, target: Path, fmt: str, bitrate: str) -> tuple[bool, str]:
    """Run one conversion. Returns (ok, message)."""
    # Opus only accepts 8, 12, 16, 24 or 48 kHz. It is not a limitation of ffmpeg but
    # of the format: Opus was designed around those rates and rejects anything else,
    # so asking for the usual 44.1 kHz fails with "Specified sample rate not supported".
    # MP3 has no such restriction, and 44.1 is its native home.
    if fmt == "opus":
        codec = ["-c:a", "libopus", "-b:a", bitrate, "-vbr", "on"]
        rate = "48000"
    else:
        codec = ["-c:a", "libmp3lame", "-b:a", bitrate]
        rate = "44100"
    command = [
        ffmpeg, "-nostdin", "-loglevel", "error", "-y",
        "-i", str(source),
        "-ac", "1",              # mix down to mono
        "-ar", rate,
        "-map_metadata", "-1",   # drop the source metadata; ours lives in the JSON
        *codec, str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    # ffmpeg creates the output file BEFORE it discovers it cannot encode, so a failed
    # run leaves a zero-byte file behind. That file then looks finished to any check
    # that only asks "does it exist", and the job silently skips it forever after.
    # Delete it here, and treat empty files as missing below. Same lesson as the
    # .part rename in the downloader: never leave a half-thing that looks whole.
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        detail = result.stderr.strip().splitlines()[-1][:90] if result.stderr else "no output produced"
        return False, detail
    return True, f"{target.stat().st_size / 1_048_576:.2f}MB"


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcode archival audio for the web.")
    parser.add_argument("--format", choices=("opus", "mp3"), default="opus",
                        help="opus is smaller and supported everywhere modern; mp3 reaches further back")
    parser.add_argument("--bitrate", default="64k",
                        help="64k mono Opus is ample for a voice carrying across a city")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--from-previews", action="store_true",
                        help="transcode the fetched preview MP3s in sawt_web/ rather than "
                             "the masters in sawt_audio/")
    args = parser.parse_args()

    # Which pile are we converting? The masters are the ideal source, but most
    # recordings only have a preview so far, and a 26MB MP3 is no kinder to a
    # listener than a 26MB WAV. Re-encoding lossy to lossy costs some quality; it is
    # the right trade until the masters arrive, and re-running from the masters later
    # overwrites these with something cleaner.
    source_dir = WEB_DIR if args.from_previews else SOURCE_DIR
    only_suffix = ".mp3" if args.from_previews else None
    if not source_dir.exists():
        raise SystemExit("Nothing to convert. Run freesound_download.py first.")
    keep_awake("the transcode")
    ffmpeg = find_ffmpeg()
    print(f"Using {ffmpeg}")

    WEB_DIR.mkdir(exist_ok=True)
    suffix = ".opus" if args.format == "opus" else ".mp3"
    sources = sorted(p for p in source_dir.iterdir()
                     if p.is_file() and p.suffix.lower() != ".part"
                     and (only_suffix is None or p.suffix.lower() == only_suffix))
    def already_done(source: Path) -> bool:
        out = WEB_DIR / (source.stem + suffix)
        return out.exists() and out.stat().st_size > 1024   # an empty file is not a conversion

    todo = [p for p in sources if not already_done(p)]
    label = "preview" if args.from_previews else "archival"
    print(f"{len(sources)} {label} files, {len(sources) - len(todo)} already converted, "
          f"{len(todo)} to do.")
    if args.limit:
        todo = todo[:args.limit]

    done = failed = 0
    before = after = 0.0
    for index, source in enumerate(todo, start=1):
        target = WEB_DIR / (source.stem + suffix)
        ok, message = encode(ffmpeg, source, target, args.format, args.bitrate)
        size_in = source.stat().st_size / 1_048_576
        if ok:
            done += 1
            before += size_in
            after += target.stat().st_size / 1_048_576
            print(f"  [{index}/{len(todo)}] {source.name:<20} {size_in:>7.1f}MB -> {message}",
                  flush=True)
        else:
            failed += 1
            print(f"  [{index}/{len(todo)}] FAILED {source.name}: {message}", flush=True)

    if done:
        print(f"\n{done} converted, {failed} failed.")
        print(f"{before:.0f}MB of masters became {after:.0f}MB of web audio "
              f"({100 * after / before:.0f}% of the size).")

    # Point each record at its streaming copy, keeping the archival path separate.
    if CANDIDATES.exists():
        items = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        linked = 0
        for c in items:
            local = c.get("local_audio") or (c.get("web_audio") if args.from_previews else None)
            if not local:
                continue
            # local may have been written on Windows with backslashes. Split on both
            # separators so this works whichever machine produced the file.
            stem = Path(local.replace("\\", "/")).stem
            web = WEB_DIR / (stem + suffix)
            if web.exists():
                # Forward slashes: a browser will not resolve a Windows backslash path.
                c["web_audio"] = str(Path("sawt_web") / web.name).replace("\\", "/")
                if not args.from_previews:
                    c["archival_audio"] = local
                linked += 1
        CANDIDATES.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Linked {linked} records to their streaming copy.")


if __name__ == "__main__":
    main()
