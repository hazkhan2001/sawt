"""
freesound_download.py
Get the real files, so Sawt hosts its own audio instead of hotlinking Freesound.

Why this script has to exist:
  The token you have been using is fine for SEARCHING. It cannot download. Freesound
  gates the original files behind OAuth2, which is a different thing entirely, and
  spec rule 10 says every file we use must be self-hosted. Right now 150 of 228
  ready recordings are links to Freesound's servers, which is a rule 10 breach and a
  map that goes silent the day they block hotlinking.

The OAuth2 flow, in plain terms. There are three parties: you (the human), Freesound
(which holds the files), and this script (which wants them on your behalf). The point
of the dance is that the script never sees your Freesound password.

  1. The script sends you to a Freesound page that says "sawt-harvester wants access".
  2. You say yes. Freesound gives you a short code.
  3. You paste the code back here. The script swaps it, plus the client secret, for an
     access token. That swap happens server to server, so the code alone is useless to
     anyone who intercepts it.
  4. The access token works for 24 hours. A refresh token renews it without asking you
     again. Both are stored in .freesound_oauth.json, which is gitignored.

Run:  python freesound_download.py --login      (once, then again every few months)
      python freesound_download.py              (downloads what is missing)
      python freesound_download.py --limit 20   (try a few first)
"""

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import requests

from config import load_secret, keep_awake

SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"
AUDIO_DIR = SCRIPT_DIR / "sawt_audio"
TOKEN_PATH = SCRIPT_DIR / ".freesound_oauth.json"

AUTHORIZE_URL = "https://freesound.org/apiv2/oauth2/authorize/"
TOKEN_URL = "https://freesound.org/apiv2/oauth2/access_token/"
HEADERS = {"User-Agent": "SawtHarvester/0.3 (Sawt heritage sound map)"}

# Freesound's access tokens last 24 hours. Refreshing a minute before the deadline
# rather than a second after avoids a race where the token dies mid-download.
EXPIRY_MARGIN_SECONDS = 120

# Freesound publishes two separate budgets, and downloads are on the strict one:
#     general requests   60 per minute, 2000 per day
#     DOWNLOADS          30 per minute,  500 per day
# One request every 2.1 seconds is 28 a minute, comfortably under 30. The earlier
# default of 1.0 s was 60 a minute, double the download limit, which is why every
# single request came back 429.
DOWNLOAD_SLEEP_SECONDS = 2.1
PROBE_SLEEP_SECONDS = 1.1        # 55 a minute, under the general limit of 60


def credentials() -> tuple[str, str]:
    """Client id and client secret, from .env. The secret is the same string as the API key."""
    client_id = load_secret("FREESOUND_CLIENT_ID")
    client_secret = load_secret("FREESOUND_CLIENT_SECRET") or load_secret("FREESOUND_TOKEN")
    if not client_id or not client_secret:
        raise SystemExit(
            "Add these to .env (both are on https://freesound.org/apiv2/apply):\n"
            "  FREESOUND_CLIENT_ID=your_client_id\n"
            "  FREESOUND_CLIENT_SECRET=your_api_key")
    return client_id, client_secret


def save_tokens(payload: dict) -> None:
    """Store the tokens with an absolute expiry, not the relative one the API returns."""
    # The API says "expires_in: 86400", meaning seconds from now. Storing that number
    # is useless tomorrow. Storing now + 86400 is a fact that stays true.
    payload = dict(payload)
    payload["expires_at"] = time.time() + float(payload.get("expires_in", 86400))
    TOKEN_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def login() -> None:
    """Step 1 and 2: send the human to Freesound, take back the code they are given."""
    client_id, client_secret = credentials()
    url = f"{AUTHORIZE_URL}?client_id={client_id}&response_type=code"
    print("\n1. Open this in a browser and click 'Authorize':\n")
    print(f"   {url}\n")
    print("2. Freesound will show you a short code, or put one in the address bar")
    print("   after 'code='. Copy it.\n")
    code = input("3. Paste the code here: ").strip()
    if not code:
        raise SystemExit("No code given.")

    response = requests.post(TOKEN_URL, headers=HEADERS, timeout=30, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
    })
    if response.status_code != 200:
        raise SystemExit(f"Freesound refused the code: {response.status_code} {response.text[:200]}")
    save_tokens(response.json())
    print(f"\nLogged in. Tokens saved to {TOKEN_PATH.name} (gitignored).")


def access_token() -> str:
    """A valid access token, refreshing it silently if the stored one has expired."""
    if not TOKEN_PATH.exists():
        raise SystemExit("Not logged in yet. Run: python freesound_download.py --login")
    stored = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))

    if stored.get("expires_at", 0) > time.time() + EXPIRY_MARGIN_SECONDS:
        return stored["access_token"]

    client_id, client_secret = credentials()
    print("Access token expired, refreshing...")
    response = requests.post(TOKEN_URL, headers=HEADERS, timeout=30, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": stored["refresh_token"],
    })
    if response.status_code != 200:
        raise SystemExit("Refresh failed. Run --login again.\n"
                         f"{response.status_code} {response.text[:200]}")
    save_tokens(response.json())
    return response.json()["access_token"]


def get_json(url: str, params: dict, token: str) -> dict:
    r = requests.get(url, params=params, timeout=30,
                     headers={**HEADERS, "Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise requests.RequestException(f"{r.status_code}")
    return r.json()


def sound_id(page_url: str) -> str | None:
    import re
    match = re.search(r"/sounds/(\d+)", page_url or "")
    return match.group(1) if match else None


def download(sid: str, token: str, destination: Path, max_mb: float) -> tuple[bool, str]:
    """
    Fetch one original file. Returns (ok, message).

    stream=True keeps the response body on the socket instead of pulling it all into
    memory, so a 200MB flac does not become 200MB of Python process.
    """
    url = f"https://freesound.org/apiv2/sounds/{sid}/download/"
    try:
        r = requests.get(url, headers={**HEADERS, "Authorization": f"Bearer {token}"},
                         timeout=120, stream=True, allow_redirects=True)
    except requests.RequestException as err:
        return False, f"{type(err).__name__}"

    if r.status_code == 401:
        return False, "401 not authorised (token may have been revoked)"
    if r.status_code == 429:
        # The body says which budget ran out. "per minute" clears on its own in a
        # minute; "per day" does not clear until tomorrow, and grinding through 150
        # more requests to discover that is pure waste. Reading the detail is the
        # difference between waiting a minute and wasting an evening.
        try:
            detail = r.json().get("detail", "")
        except ValueError:
            detail = r.text[:120]
        daily = "day" in detail.lower()
        return False, f"429 {'DAILY LIMIT' if daily else 'rate limited'}: {detail[:90]}"
    if r.status_code != 200:
        return False, f"{r.status_code}"

    size_mb = int(r.headers.get("Content-Length", 0)) / 1_048_576
    if max_mb and size_mb > max_mb:
        r.close()
        return False, f"skipped, {size_mb:.0f}MB is over the --max-mb limit"

    # Freesound puts the real filename in Content-Disposition; fall back to the id.
    disposition = r.headers.get("Content-Disposition", "")
    suffix = ".bin"
    if "filename=" in disposition:
        name = disposition.split("filename=")[-1].strip('"; ')
        if "." in name:
            suffix = "." + name.rsplit(".", 1)[-1].lower()

    final = destination / f"{sid}{suffix}"
    partial = final.with_suffix(final.suffix + ".part")
    # Write to a .part file and rename only on success. A half-written file that looks
    # finished is how a resumable job quietly corrupts itself.
    with open(partial, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
    partial.rename(final)
    return True, f"{final.name} ({final.stat().st_size / 1_048_576:.1f}MB)"


def probe(wanted: list, token: str) -> None:
    """
    Ask Freesound how big each original is, before committing to the download.

    The API will tell you filesize and format for free. Finding out by downloading
    258MB and then deciding you did not want it is the expensive way to learn.
    """
    print(f"Asking Freesound about {len(wanted)} files...\n")
    sizes, formats, failures = [], Counter(), 0
    for index, (sid, c) in enumerate(wanted, start=1):
        try:
            data = get_json(f"https://freesound.org/apiv2/sounds/{sid}/",
                            params={"fields": "filesize,type,duration,samplerate,channels"},
                            token=token)
        except requests.RequestException:
            failures += 1
            continue
        mb = (data.get("filesize") or 0) / 1_048_576
        sizes.append((mb, sid, c["title"], data.get("type", "?")))
        formats[data.get("type", "?")] += 1
        if index % 25 == 0:
            print(f"  {index}/{len(wanted)}...", flush=True)
        time.sleep(PROBE_SLEEP_SECONDS)

    sizes.sort(reverse=True)
    total = sum(mb for mb, *_ in sizes)
    print(f"\n{len(sizes)} files, {total/1024:.1f} GB in total ({failures} could not be checked)")
    print("\nby format:")
    for fmt, n in formats.most_common():
        subtotal = sum(mb for mb, _, _, f in sizes if f == fmt)
        print(f"  {n:>4}  {fmt:<6} {subtotal/1024:>6.2f} GB")
    print("\nlargest ten:")
    for mb, sid, title, fmt in sizes[:10]:
        print(f"  {mb:>7.1f} MB  {fmt:<5} {title[:52]}")
    print("\nwhat different --max-mb values would fetch:")
    print("\n  NOTE: that was ~150 requests. Wait a minute before downloading,")
    print("  or the first downloads will be refused for exceeding the per-minute limit.")
    for cap in (20, 60, 150, 400, 10_000):
        kept = [s for s in sizes if s[0] <= cap]
        label = "everything" if cap == 10_000 else f"{cap} MB"
        print(f"  {label:<11} {len(kept):>4} files, {sum(m for m, *_ in kept)/1024:>6.2f} GB")


WEB_DIR = SCRIPT_DIR / "sawt_web"


def fetch_previews(wanted: list, items: list, limit: int = 0) -> None:
    """
    Self-host the preview MP3s instead of the originals.

    Why this is a legitimate route rather than a corner cut:

      The 500-a-day cap applies to the API's /download/ endpoint, which serves the
      original master. The preview files sit on cdn.freesound.org, a plain file
      server, and fetching one is an ordinary HTTP GET against no API quota at all.

      The licence is what actually decides this. CC0 and CC BY both permit copying
      and redistributing the work, and a preview is the same work at a lower
      bitrate. Rule 10 in the spec forbids HOTLINKING, not lower quality: the sin is
      making someone else's server carry your traffic, and downloading a copy to
      host yourself is precisely the fix.

      128kbps stereo MP3 is also better than the 96kbps mono we were going to
      transcode the masters down to anyway. For a map of voices carrying across a
      city, it is more than enough.

    The originals remain worth having as archival masters, but they are a backfill
    job at 500 a day, not a prerequisite for shipping.
    """
    WEB_DIR.mkdir(exist_ok=True)
    todo = []
    for sid, c in wanted:
        if c.get("local_audio"):
            continue                      # we already have the real master for this one
        url = c.get("audio_url") or ""
        if url.startswith("http"):
            todo.append((sid, c, url))
    if limit:
        todo = todo[:limit]

    print(f"{len(todo)} preview files to fetch from cdn.freesound.org "
          f"(no API quota involved).\n")
    ok = failed = 0
    for index, (sid, c, url) in enumerate(todo, start=1):
        suffix = ".mp3" if ".mp3" in url else Path(url).suffix or ".mp3"
        target = WEB_DIR / f"{sid}{suffix}"
        if target.exists() and target.stat().st_size > 1024:
            print(f"  [{index}/{len(todo)}] skip {sid}  already have it", flush=True)
            continue
        partial = target.with_suffix(target.suffix + ".part")
        # Print BEFORE the request, not after. A line that only appears on success
        # tells you nothing while you are waiting, and "nothing" is exactly the state
        # you most need information about.
        print(f"  [{index}/{len(todo)}] .... {sid}  {c['title'][:44]}", end="", flush=True)
        try:
            # A tuple timeout is (connect, read). With stream=True the read timeout
            # applies to EACH socket read, so a stalled body fails in 20s instead of
            # hanging until someone notices. A single number sets both.
            r = requests.get(url, headers=HEADERS, timeout=(10, 20), stream=True)
            if r.status_code != 200:
                print(f"  ->  FAIL {r.status_code} {r.reason}", flush=True)
                failed += 1
                continue
            with open(partial, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
            partial.rename(target)
        except requests.RequestException as err:
            print(f"  ->  FAIL {type(err).__name__}", flush=True)
            partial.unlink(missing_ok=True)
            failed += 1
            continue

        mb = target.stat().st_size / 1_048_576
        c["web_audio"] = str(Path("sawt_web") / target.name)
        c["audio_quality"] = "preview"     # honest label: not the master
        ok += 1
        print(f"  ->  {mb:.2f}MB", flush=True)
        time.sleep(0.3)                    # a CDN, but still someone else's bandwidth
        if index % 25 == 0:
            CANDIDATES.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    CANDIDATES.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(p.stat().st_size for p in WEB_DIR.iterdir() if p.is_file()) / 1_048_576
    print(f"\n{ok} fetched, {failed} failed. sawt_web/ now holds {total:.0f}MB.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Freesound originals for self-hosting.")
    parser.add_argument("--login", action="store_true", help="run the OAuth2 login once")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many downloads")
    parser.add_argument("--max-mb", type=float, default=0,
                        help="skip files larger than this in MB (0 = no limit)")
    parser.add_argument("--all", action="store_true",
                        help="include items that are not Tier A or not placed")
    parser.add_argument("--sleep", type=float, default=DOWNLOAD_SLEEP_SECONDS,
                        help=f"seconds between downloads (default {DOWNLOAD_SLEEP_SECONDS}, "
                             "which is 28 a minute against Freesound's limit of 30)")
    parser.add_argument("--previews", action="store_true",
                        help="fetch the preview MP3s from the CDN instead of the originals. "
                             "No API quota, good enough to ship, satisfies rule 10")
    parser.add_argument("--probe", action="store_true",
                        help="ask how big everything is, without downloading anything")
    args = parser.parse_args()

    if args.login:
        login()
        return

    if not CANDIDATES.exists():
        raise SystemExit(f"No results at {CANDIDATES}.")
    items = json.loads(CANDIDATES.read_text(encoding="utf-8"))

    wanted = []
    for c in items:
        if c.get("source") != "freesound":
            continue
        if not args.all and not (c["tier"] == "A" and c.get("lat") is not None):
            continue
        sid = sound_id(c.get("page_url", ""))
        if sid:
            wanted.append((sid, c))

    if args.previews:
        keep_awake("the preview download")
        fetch_previews(wanted, items, args.limit)
        return

    AUDIO_DIR.mkdir(exist_ok=True)
    have = {p.stem for p in AUDIO_DIR.iterdir() if p.is_file()}
    todo = [(sid, c) for sid, c in wanted if sid not in have]

    print(f"{len(wanted)} Freesound recordings in scope, {len(have)} already downloaded, "
          f"{len(todo)} to fetch.")
    if not todo:
        return
    if args.limit:
        todo = todo[:args.limit]
        print(f"Limiting this run to {len(todo)}.")

    keep_awake("the download")
    token = access_token()

    if args.probe:
        probe(wanted, token)
        return

    ok = failed = 0
    consecutive = 0
    minutes = len(todo) * args.sleep / 60
    print(f"Pacing at {args.sleep}s per file to stay under Freesound's 30 downloads "
          f"a minute. Minimum run time about {minutes:.0f} minutes.\n")
    # A while loop rather than a for loop, because a throttled file has to be RETRIED,
    # not skipped, and `continue` inside a for loop always advances. The index moves
    # only when a file is finished with, successfully or permanently.
    index = 0
    while index < len(todo):
        sid, c = todo[index]
        success, message = download(sid, token, AUDIO_DIR, args.max_mb)
        mark = "ok  " if success else "FAIL"
        print(f"  [{index + 1}/{len(todo)}] {mark} {sid}  {c['title'][:44]}  {message}", flush=True)
        if success:
            ok += 1
            consecutive = 0
            index += 1
            # Point the record at the local file. The remote URL is kept, because the
            # attribution requirement means we must always be able to say where it came from.
            c["local_audio"] = str(Path("sawt_audio") / f"{sid}{Path(message.split()[0]).suffix}")
        else:
            if "DAILY LIMIT" in message:
                print("\n  Daily download quota reached (500 a day). Stopping.")
                print("  Re-run tomorrow; everything already downloaded is skipped.")
                break
            if "429" in message:
                consecutive += 1
                if consecutive >= 4:
                    print("\n  Four refusals in a row. Freesound is still throttling us.")
                    print("  Stop here, wait five minutes, and re-run. Nothing is lost:")
                    print("  already-downloaded files are skipped on the next run.")
                    break
                # Widening wait rather than a flat 60s. A fixed pause that is too short
                # just spends the next request confirming we are still throttled.
                wait = 30 * (2 ** (consecutive - 1))
                print(f"    throttled, waiting {wait}s (attempt {consecutive} of 4)")
                time.sleep(wait)
                continue        # index unchanged, so the same file is tried again
            # Any other failure is permanent for this run: record it and move on.
            failed += 1
            consecutive = 0
            index += 1
        time.sleep(args.sleep)

        if index % 20 == 0:
            CANDIDATES.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    CANDIDATES.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    total_mb = sum(p.stat().st_size for p in AUDIO_DIR.iterdir() if p.is_file()) / 1_048_576
    print(f"\n{ok} downloaded, {failed} failed. {AUDIO_DIR.name}/ now holds {total_mb:.0f}MB.")
    print("Re-run to continue; already-downloaded files are skipped.")


if __name__ == "__main__":
    main()
