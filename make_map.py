"""
make_map.py
A throwaway diagnostic map. Not part of the app, not kept.

Its only job is to answer questions you cannot answer by reading JSON: are the
coordinates plausible, do they cluster where they should, is anything in the ocean
because a regex grabbed the wrong number.

Real satellite imagery from Esri. No stylised or synthetic basemap.

Run:  python make_map.py            (reads sawt_candidates.json)
      python make_map.py --preview  (reads the preview file)
Opens: sawt_map.html
"""

import argparse
import json
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUT_PATH = SCRIPT_DIR / "sawt_map.html"

# The seven hubs from the spec, so you can see at a glance which ones have nothing.
HUBS = [
    ("Fez", 34.0646, -4.9737), ("Cairo", 30.0444, 31.2357),
    ("Aleppo", 36.2021, 37.1343), ("Konya", 37.8746, 32.4932),
    ("Isfahan", 32.6539, 51.6660), ("Delhi", 28.6139, 77.2090),
    ("Kashgar", 39.4704, 75.9898),
]

TIER_COLOURS = {"A": "#4ade80", "B": "#fbbf24", "C": "#f87171"}


def load(preview: bool) -> list[dict]:
    name = "sawt_candidates_preview.json" if preview else "sawt_candidates.json"
    path = SCRIPT_DIR / name
    if not path.exists():
        raise SystemExit(f"No results at {path}. Run sawt_harvester.py first.")
    print(f"Reading {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot harvested recordings on a real map.")
    parser.add_argument("--preview", action="store_true", help="read the preview results file")
    args = parser.parse_args()

    items = load(args.preview)
    placed = [c for c in items
              if c.get("lat") is not None and c.get("lng") is not None
              and -90 <= c["lat"] <= 90 and -180 <= c["lng"] <= 180]

    print(f"{len(placed)} of {len(items)} candidates have usable coordinates")
    print("  by tier:", dict(Counter(c["tier"] for c in placed)))

    # json.dumps turns the Python list into JavaScript's own notation, which is the
    # simplest safe way to hand data to a page. No string concatenation, no escaping bugs.
    payload = json.dumps([{
        "lat": c["lat"], "lng": c["lng"],
        "title": c["title"], "tier": c["tier"],
        "license": c.get("license", ""), "source": c.get("source", ""),
        "url": c.get("page_url", ""), "audio": c.get("audio_url") or "",
        "recitation": c.get("category") == "recitation",
        "found_by": c.get("found_by") or "",
    } for c in placed], ensure_ascii=False)

    html = HTML_TEMPLATE.replace("__POINTS__", payload).replace(
        "__HUBS__", json.dumps(HUBS)).replace(
        "__COLOURS__", json.dumps(TIER_COLOURS))
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")
    print("Open it in a browser. Green = Tier A, amber = B, red = C, hollow = recitation.")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sawt: harvest diagnostic map</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
  html, body { margin: 0; height: 100%; background: #0b0f14; color: #e8eaed;
               font: 14px/1.5 system-ui, sans-serif; }
  #map { height: 100%; }
  .panel { position: absolute; z-index: 1000; top: 12px; right: 12px; width: 260px;
           background: rgba(11,15,20,.92); border: 1px solid #2a3340; border-radius: 8px;
           padding: 12px 14px; }
  .panel h1 { margin: 0 0 8px; font-size: 15px; font-weight: 600; }
  .row { display: flex; justify-content: space-between; padding: 2px 0; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
         margin-right: 6px; vertical-align: middle; }
  .muted { color: #8b97a6; font-size: 12px; }
  .leaflet-popup-content { font: 13px/1.45 system-ui, sans-serif; }
  .leaflet-popup-content b { display: block; margin-bottom: 4px; }
  audio { width: 230px; margin-top: 6px; }
</style>
</head>
<body>
<div id="map"></div>
<div class="panel">
  <h1>Harvest diagnostic</h1>
  <div id="counts"></div>
  <p class="muted" id="note"></p>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const POINTS = __POINTS__;
const HUBS = __HUBS__;
const COLOURS = __COLOURS__;

const map = L.map('map', { worldCopyJump: true }).setView([28, 35], 3);

// Real satellite imagery, not a stylised basemap.
L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  { attribution: 'Imagery: Esri, Maxar, Earthstar Geographics', maxZoom: 17 }
).addTo(map);

// Spec hubs, so empty ones are obvious.
HUBS.forEach(([name, lat, lng]) => {
  L.marker([lat, lng], { opacity: 0.9 }).addTo(map)
    .bindTooltip(name, { permanent: true, direction: 'right', className: 'hub' });
});

const counts = {};
POINTS.forEach(p => {
  counts[p.tier] = (counts[p.tier] || 0) + 1;
  const marker = L.circleMarker([p.lat, p.lng], {
    radius: 5,
    color: COLOURS[p.tier] || '#94a3b8',
    weight: 2,
    fillColor: COLOURS[p.tier] || '#94a3b8',
    fillOpacity: p.recitation ? 0 : 0.65
  }).addTo(map);

  const audio = p.audio ? `<audio controls preload="none" src="${p.audio}"></audio>` : '';
  marker.bindPopup(
    `<b>${p.title}</b>`
    + `<span class="muted">${p.source} &middot; Tier ${p.tier} &middot; ${p.license}</span><br>`
    + (p.found_by ? `<span class="muted">found by: ${p.found_by}</span><br>` : '')
    + (p.recitation ? '<span class="muted">quarantined recitation</span><br>' : '')
    + `<a href="${p.url}" target="_blank" rel="noopener">source page</a>`
    + audio
  );
});

document.getElementById('counts').innerHTML =
  ['A','B','C'].filter(t => counts[t]).map(t =>
    `<div class="row"><span><span class="dot" style="background:${COLOURS[t]}"></span>Tier ${t}</span>`
    + `<span>${counts[t]}</span></div>`).join('')
  + `<div class="row" style="border-top:1px solid #2a3340;margin-top:6px;padding-top:6px">`
  + `<span>placed</span><span>${POINTS.length}</span></div>`;

document.getElementById('note').textContent =
  'Hollow circles are quarantined recitation. Pins are the seven spec hubs.';
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
