"""
review.py
Listen to every candidate and approve, reject or flag it. The step the spec has
said from the beginning must happen before anything ships.

Why this is a small web SERVER and not just an HTML file:

    A page opened with file:// cannot write to your disk. That is a browser security
    rule, not a limitation we can code around, and it is a good rule: a web page
    should not be able to edit your files. So we run a tiny server on your own
    machine. The page asks it for the queue, and posts each decision back, and the
    server is the thing with permission to write.

    It is about forty lines. A "server" is not a big idea: it is a program that
    listens on a port and answers requests.

Decisions are stored in sawt_reviews.json, NOT in sawt_candidates.json. That
separation matters: the harvester overwrites its own output every run, and your
listening time must never be destroyed by re-running a script.

Run:  python review.py
      python review.py --export     (write the approved set to sawt_approved.json)
"""

import argparse
import json
import webbrowser
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from genres import classify
from gazetteer import nearest_place

SCRIPT_DIR = Path(__file__).resolve().parent
CANDIDATES = SCRIPT_DIR / "sawt_candidates.json"
REVIEWS = SCRIPT_DIR / "sawt_reviews.json"
APPROVED = SCRIPT_DIR / "sawt_approved.json"
PORT = 8731
SCOPE = "map"            # set from the command line in main()


def load_reviews() -> dict:
    if REVIEWS.exists():
        return json.loads(REVIEWS.read_text(encoding="utf-8"))
    return {}


def build_queue(scope: str = "map") -> list:
    """
    Everything worth a human's attention, ordered so one place is heard together.

    scope="map" (the default) is the only queue that earns your time right now:
    recordings that are open-licensed, playable, AND carry coordinates, because a
    recording with no location cannot go on a globe however good it is. It also
    leaves out recitation, which is quarantined until the project has the separate
    category section 8 requires, and reviewing it as music would be exactly the
    mistake that rule exists to prevent.

    scope="all" opens the gate on the rest, for when the gazetteer or task 7 has
    caught up. Reviewing 528 items to ship 240 is how a review step gets abandoned.
    """
    items = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    queue = []
    for c in items:
        if c["tier"] == "C":
            continue                       # non-commercial only; not a judgement call
        if not c.get("playable"):
            continue
        if scope == "map":
            if c.get("lat") is None or c.get("lng") is None:
                continue
            if c.get("category") == "recitation":
                continue
        audio = c.get("web_audio") or c.get("local_audio") or c.get("audio_url")
        if not audio:
            continue
        genre, family, label = classify(c)
        near = nearest_place(c["lat"], c["lng"]) if c.get("lat") is not None else None
        place = (f"{near['city']}, {near['country']}" if near and near["country"]
                 else (near["city"] if near else "Location unknown"))

        # Rights flags worth seeing BEFORE deciding, not after.
        flags = []
        lic = (c.get("license") or "").lower()
        if "sa" in lic.replace("-", " ").split():
            flags.append("share-alike obligations")
        if "nd" in lic.replace("-", " ").split():
            flags.append("NoDerivatives: no trimming")
        if "by" in lic and not c.get("attribution"):
            flags.append("CC BY with no credit recorded")
        if c.get("category") == "recitation":
            flags.append("recitation: separate category, never music")
        if c["tier"] == "B":
            flags.append("Tier B: licence needs a human call")
        if not (c.get("web_audio") or c.get("local_audio")):
            flags.append("not self-hosted yet")

        queue.append({
            "id": c["page_url"],
            "title": c["title"],
            "audio": str(audio).replace("\\", "/"),
            "place": place,
            "genre": label,
            "tier": c["tier"],
            "license": c.get("license", ""),
            "attribution": c.get("attribution") or "",
            "source": c.get("source", ""),
            "url": c.get("page_url", ""),
            "seconds": c.get("duration_seconds"),
            "basis": c.get("place_basis") or "geotag",
            "flags": flags,
            "sortKey": place,
        })
    # Grouping by place means you hear Fez's twenty-two in a row, which makes
    # duplicates and near-identical takes obvious in a way a shuffled list never does.
    queue.sort(key=lambda row: (row["sortKey"], row["genre"], row["title"]))
    return queue


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SCRIPT_DIR), **kwargs)

    def log_message(self, *args):
        pass                               # the console is for progress, not access logs

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/queue":
            self._json({"queue": build_queue(SCOPE), "reviews": load_reviews()})
            return
        super().do_GET()                   # audio files and anything else on disk

    def do_POST(self):
        if self.path != "/api/decision":
            self._json({"error": "unknown"}, 404)
            return
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        reviews = load_reviews()
        if payload.get("decision") is None:
            reviews.pop(payload["id"], None)          # undo
        else:
            reviews[payload["id"]] = {
                "decision": payload["decision"],
                "note": payload.get("note", ""),
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        # Write on every decision. Batching would be faster and would lose an hour of
        # listening the first time something crashes.
        REVIEWS.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
        self._json({"ok": True, "count": len(reviews)})


def export() -> None:
    reviews = load_reviews()
    items = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    approved = [c for c in items
                if reviews.get(c["page_url"], {}).get("decision") == "approve"]
    APPROVED.write_text(json.dumps(approved, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {}
    for entry in reviews.values():
        counts[entry["decision"]] = counts.get(entry["decision"], 0) + 1
    print(f"{len(reviews)} decisions recorded: {counts}")
    print(f"Wrote {len(approved)} approved records to {APPROVED.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Review harvested recordings by ear.")
    parser.add_argument("--export", action="store_true",
                        help="write the approved set and exit")
    parser.add_argument("--all", action="store_true",
                        help="also queue unplaced recordings and quarantined recitation")
    args = parser.parse_args()
    scope = "all" if args.all else "map"
    if args.export:
        export()
        return

    global SCOPE
    SCOPE = scope
    queue = build_queue(scope)
    reviews = load_reviews()
    print(f"{len(queue)} recordings to review, {len(reviews)} already decided.")
    print(f"\nOpen http://localhost:{PORT}/  (opening it now)")
    print("Keys:  space play/pause   a approve   r reject   f flag   s skip")
    print("       left/right move    u undo      Ctrl+C here when you are done\n")
    webbrowser.open(f"http://localhost:{PORT}/")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Decisions are saved in sawt_reviews.json.")
        print("Run  python review.py --export  to write the approved set.")


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Sawt review</title>
<style>
 :root{--bg:#0b0e13;--panel:#131820;--line:#26303d;--ink:#eef2f7;--ink2:#93a1b2;
       --ok:#199e70;--no:#d95926;--flag:#c98500;}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);
      font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
 .wrap{max-width:780px;margin:0 auto;padding:28px 20px 80px}
 .bar{height:6px;background:var(--line);border-radius:99px;overflow:hidden;margin-bottom:6px}
 .bar i{display:block;height:100%;background:var(--ok);transition:width .2s}
 .stats{display:flex;gap:16px;color:var(--ink2);font-size:13px;margin-bottom:22px}
 .stats b{color:var(--ink);font-weight:600}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px}
 .place{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:#7fb2f0}
 h1{font-size:20px;margin:6px 0 10px;line-height:1.3}
 .meta{color:var(--ink2);font-size:13px}
 .flags{margin:12px 0 0}
 .flag{display:inline-block;font-size:12px;padding:3px 9px;border-radius:99px;
       background:rgba(201,133,0,.14);color:#ffca5f;border:1px solid rgba(201,133,0,.35);
       margin:0 6px 6px 0}
 audio{width:100%;margin:18px 0 6px}
 .btns{display:flex;gap:10px;margin-top:16px}
 button{flex:1;padding:13px 0;font:inherit;font-weight:600;border-radius:10px;
        border:1px solid var(--line);background:#182130;color:var(--ink);cursor:pointer}
 button:hover{filter:brightness(1.25)}
 .ok{border-color:var(--ok);color:#8ee9c4}
 .no{border-color:var(--no);color:#ffb08c}
 .fl{border-color:var(--flag);color:#ffd98a}
 .decided{margin-top:14px;font-size:13px;color:var(--ink2)}
 .keys{margin-top:26px;color:var(--ink2);font-size:12.5px;line-height:1.9}
 kbd{background:#1b2431;border:1px solid var(--line);border-radius:5px;padding:1px 6px;
     font:12px ui-monospace,monospace}
 a{color:#7fb2f0}
 .guide{margin-top:20px;padding:14px 16px;background:#101720;border:1px solid var(--line);
        border-radius:10px;color:var(--ink2);font-size:13px}
 .guide b{color:var(--ink)}
 textarea{width:100%;margin-top:10px;background:#0e141c;color:var(--ink);
          border:1px solid var(--line);border-radius:8px;padding:8px;font:inherit;resize:vertical}
</style></head><body><div class="wrap">
<div class="bar"><i id="bar"></i></div>
<div class="stats">
  <span><b id="pos">0</b> of <b id="total">0</b></span>
  <span style="color:#8ee9c4"><b id="nOk">0</b> approved</span>
  <span style="color:#ffb08c"><b id="nNo">0</b> rejected</span>
  <span style="color:#ffd98a"><b id="nFl">0</b> flagged</span>
  <span><b id="nLeft">0</b> left</span>
</div>

<div class="card">
  <div class="place" id="place"></div>
  <h1 id="title"></h1>
  <div class="meta" id="meta"></div>
  <div class="flags" id="flags"></div>
  <audio id="au" controls autoplay></audio>
  <div class="meta"><a id="src" target="_blank" rel="noopener">source page</a></div>
  <textarea id="note" rows="2" placeholder="note (optional), saved with the decision"></textarea>
  <div class="btns">
    <button class="ok" onclick="decide('approve')">Approve <kbd>a</kbd></button>
    <button class="no" onclick="decide('reject')">Reject <kbd>r</kbd></button>
    <button class="fl" onclick="decide('flag')">Flag <kbd>f</kbd></button>
    <button onclick="move(1)">Skip <kbd>s</kbd></button>
  </div>
  <div class="decided" id="decided"></div>
</div>

<div class="guide">
  <b>What you are judging.</b> Is it actually what the title claims? Is the sound usable,
  or is it ninety per cent traffic? Does anything smell like a commercial upload rather
  than a freely given one? Does it add something the map does not already have, or is it
  the fourth near-identical take from the same rooftop?
</div>

<div class="keys">
  <kbd>space</kbd> play/pause &nbsp; <kbd>a</kbd> approve &nbsp; <kbd>r</kbd> reject &nbsp;
  <kbd>f</kbd> flag &nbsp; <kbd>s</kbd> skip &nbsp; <kbd>u</kbd> undo this one<br>
  <kbd>&larr;</kbd> <kbd>&rarr;</kbd> move &nbsp; <kbd>j</kbd> jump to first undecided
</div>
</div><script>
let Q=[],R={},i=0;
const el=id=>document.getElementById(id);
const au=el('au');

fetch('/api/queue').then(r=>r.json()).then(d=>{
  Q=d.queue; R=d.reviews||{};
  el('total').textContent=Q.length;
  jump();
});

function stats(){
  let ok=0,no=0,fl=0;
  Object.values(R).forEach(v=>{if(v.decision==='approve')ok++;else if(v.decision==='reject')no++;else fl++;});
  el('nOk').textContent=ok; el('nNo').textContent=no; el('nFl').textContent=fl;
  el('nLeft').textContent=Q.length-Object.keys(R).length;
  el('bar').style.width=(100*Object.keys(R).length/Q.length)+'%';
}

function show(){
  const q=Q[i]; if(!q)return;
  el('pos').textContent=i+1;
  el('place').textContent=q.place;
  el('title').textContent=q.title;
  const bits=[q.genre,q.source,'Tier '+q.tier,q.license];
  if(q.attribution)bits.push('by '+q.attribution);
  if(q.seconds)bits.push(Math.round(q.seconds)+'s');
  el('meta').textContent=bits.filter(Boolean).join(' · ');
  el('flags').innerHTML=(q.flags||[]).map(f=>`<span class="flag">${f}</span>`).join('');
  el('src').href=q.url;
  au.src=q.audio;
  au.play().catch(()=>{});
  const d=R[q.id];
  el('decided').textContent=d?`recorded: ${d.decision}${d.note?' — '+d.note:''}`:'';
  el('note').value=d?d.note||'':'';
  stats();
}

function decide(decision){
  const q=Q[i]; if(!q)return;
  const note=el('note').value.trim();
  R[q.id]={decision,note};
  fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:q.id,decision,note})});
  el('note').value='';
  move(1);
}

function undo(){
  const q=Q[i]; if(!q)return;
  delete R[q.id];
  fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:q.id,decision:null})});
  show();
}

function move(step){ i=Math.max(0,Math.min(Q.length-1,i+step)); show(); }
function jump(){ const n=Q.findIndex(q=>!R[q.id]); i=n<0?0:n; show(); }

addEventListener('keydown',e=>{
  if(e.target.tagName==='TEXTAREA')return;      // let the note field take its own keys
  const k=e.key.toLowerCase();
  if(k===' '){e.preventDefault(); au.paused?au.play():au.pause();}
  else if(k==='a')decide('approve');
  else if(k==='r')decide('reject');
  else if(k==='f')decide('flag');
  else if(k==='s')move(1);
  else if(k==='u')undo();
  else if(k==='arrowright')move(1);
  else if(k==='arrowleft')move(-1);
  else if(k==='j')jump();
});
</script></body></html>
"""


if __name__ == "__main__":
    main()
