"""
make_globe.py
A rotatable globe: real NASA Blue Marble imagery on a starfield, one circle per
recording, coloured by family and shaped by genre.

This is still a diagnostic and a prototype, not the Next.js app. But it uses
globe.gl, which the spec already names as the v1 globe engine, so what is learned
here carries over rather than being thrown away.

Run:  python make_globe.py
Opens: sawt_globe.html
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from genres import classify, FAMILY_LABEL
from gazetteer import nearest_place

SCRIPT_DIR = Path(__file__).resolve().parent
OUT_PATH = SCRIPT_DIR / "sawt_globe.html"

# Three hues carry the families. Three, not seven, because a point map is what the
# colour method calls an "all-pairs" form: every colour can land next to every other,
# so all 21 pairs of seven colours would have to stay distinguishable, and they cannot.
# Validated as a set against a dark surface: worst colour-blind separation dE 9.4,
# worst normal-vision separation dE 20.9, all three above 3:1 contrast.
# Genre is carried by SHAPE instead, which is why the legend shows filled and hollow
# circles. Colour and shape together give seven readable categories.
FAMILY_COLOUR = {
    "call":        "#3987e5",   # blue
    "devotional":  "#d95926",   # orange
    "music":       "#199e70",   # green
    "recitation":  "#e8eaed",   # neutral: not a music category, see spec section 8
    "other":       "#8b97a6",   # muted grey, recessive on purpose
}

# genre key -> (marker style, display order in the legend)
GENRE_STYLE = {
    "adhan":        ("filled", 1),
    "dhikr_hadra":  ("filled", 2),
    "inshad_madih": ("hollow", 3),
    "art_music":    ("filled", 4),
    "instrument":   ("hollow", 5),
    "tilawa":       ("hollow", 6),
    "ambience":     ("small",  7),
    "other":        ("small",  8),
}


def local_audio(candidate: dict) -> str:
    """
    The URL the page should play: our own copy if we have one, else the remote.

    Paths written on Windows carry backslashes, which a browser will not resolve as a
    relative URL. Converting to forward slashes is the whole of the portability fix.
    """
    for key in ("web_audio", "local_audio"):
        value = candidate.get(key)
        if value:
            return str(value).replace("\\", "/")
    return candidate.get("audio_url") or ""


def cluster_key(candidate: dict, place) -> str:
    """
    Which cluster does this recording belong to?

    Grouping by NEAREST CITY rather than by raw distance is the cheap win here: the
    gazetteer already computes it, cities are what a listener thinks in, and the
    result is stable (a recording never jumps between clusters when the map moves).
    Anything with no city within range falls back to a one-degree grid square, which
    is roughly 110km and honest about being approximate.
    """
    if place:
        return f"city:{place['city']}"
    return f"grid:{round(candidate['lat'])},{round(candidate['lng'])}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Sawt globe prototype.")
    parser.add_argument("--preview", action="store_true", help="read the preview results")
    args = parser.parse_args()

    name = "sawt_candidates_preview.json" if args.preview else "sawt_candidates.json"
    path = SCRIPT_DIR / name
    if not path.exists():
        raise SystemExit(f"No results at {path}. Run sawt_harvester.py first.")
    items = json.loads(path.read_text(encoding="utf-8"))

    placed = [c for c in items
              if c.get("lat") is not None and c.get("lng") is not None
              and -90 <= c["lat"] <= 90 and -180 <= c["lng"] <= 180]

    points, clusters, genre_counts = [], {}, Counter()
    for c in placed:
        genre, family, label = classify(c)
        genre_counts[label] += 1
        near = nearest_place(c["lat"], c["lng"])
        if near:
            place_name = f"{near['city']}, {near['country']}" if near["country"] else near["city"]
            proximity = f"{near['km']} km from {near['city']}" if near["km"] > 25 else ""
        else:
            place_name, proximity = "Location unnamed", ""

        key = cluster_key(c, near)
        cluster = clusters.setdefault(key, {
            "id": key, "place": place_name,
            "short": near["city"] if near else f"{round(c['lat'])}, {round(c['lng'])}",
            "lats": [], "lngs": [],
        })
        cluster["lats"].append(c["lat"])
        cluster["lngs"].append(c["lng"])

        points.append({
            "cluster": key, "place": place_name, "proximity": proximity,
            "lat": c["lat"], "lng": c["lng"],
            "title": c["title"], "genre": genre, "genreLabel": label,
            "family": family, "colour": FAMILY_COLOUR[family],
            "style": GENRE_STYLE[genre][0],
            "tier": c["tier"], "license": c.get("license", ""),
            "source": c.get("source", ""), "url": c.get("page_url", ""),
            # Prefer the file we own. web_audio is a path relative to this folder,
            # so the generated HTML plays a local copy and never touches Freesound's
            # servers. Falling back to the remote URL keeps unfetched items playable,
            # but every fallback is a rule 10 breach waiting to be closed.
            "audio": local_audio(c),
            "selfHosted": bool(c.get("web_audio") or c.get("local_audio")),
            "basis": c.get("place_basis") or "geotag",
            "attribution": c.get("attribution") or "",
            "seconds": c.get("duration_seconds"),
        })

    # A cluster sits at the mean of its members. For a city cluster they are all
    # within a few km of each other anyway, so the mean is not misleading.
    for cluster in clusters.values():
        cluster["lat"] = sum(cluster["lats"]) / len(cluster["lats"])
        cluster["lng"] = sum(cluster["lngs"]) / len(cluster["lngs"])
        del cluster["lats"], cluster["lngs"]

    legend = []
    for genre, family, label, _words in _rules():
        count = sum(1 for p in points if p["genre"] == genre)
        if count:
            legend.append({"genre": genre, "label": label, "colour": FAMILY_COLOUR[family],
                           "style": GENRE_STYLE[genre][0], "count": count})
    other = sum(1 for p in points if p["genre"] == "other")
    if other:
        legend.append({"genre": "other", "label": "Other", "colour": FAMILY_COLOUR["other"],
                       "style": "small", "count": other})
    legend.sort(key=lambda row: GENRE_STYLE[row["genre"]][1])

    html = (HTML_TEMPLATE
            .replace("__POINTS__", json.dumps(points, ensure_ascii=False))
            .replace("__CLUSTERS__", json.dumps(list(clusters.values()), ensure_ascii=False))
            .replace("__LEGEND__", json.dumps(legend, ensure_ascii=False)))
    OUT_PATH.write_text(html, encoding="utf-8")

    self_hosted = sum(1 for p in points if p["selfHosted"])
    print(f"{len(points)} recordings in {len(clusters)} places")
    print(f"  {self_hosted} play a self-hosted file, "
          f"{len(points) - self_hosted} still hotlink (rule 10)\n")
    for label, n in genre_counts.most_common():
        print(f"  {n:>4}  {label}")
    biggest = sorted(clusters.values(),
                     key=lambda cl: -sum(1 for p in points if p["cluster"] == cl["id"]))[:8]
    print("\nbusiest places:")
    for cl in biggest:
        n = sum(1 for p in points if p["cluster"] == cl["id"])
        print(f"  {n:>4}  {cl['place']}")
    print(f"\nWrote {OUT_PATH}")


def _rules():
    from genres import GENRE_RULES
    return GENRE_RULES


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sawt: the Islamic soundscape map</title>
<style>
  :root { --surface:#05070a; --panel:rgba(9,12,17,.92); --line:#28323f;
          --ink:#f3f5f8; --ink-2:#9daaba; --ink-3:#6b7889; --accent:#7fb2f0; }
  * { box-sizing:border-box; }
  html, body { margin:0; height:100%; background:var(--surface); color:var(--ink);
               font:14px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
               overflow:hidden; }
  #globe { position:absolute; inset:0; }
  .card { position:absolute; z-index:10; background:var(--panel); border:1px solid var(--line);
          border-radius:12px; backdrop-filter:blur(10px);
          box-shadow:0 14px 44px rgba(0,0,0,.6); }

  #legend { top:16px; left:16px; width:262px; padding:14px 16px; }
  #legend h1 { margin:0; font-size:17px; font-weight:600; letter-spacing:.02em; }
  #legend .sub { color:var(--ink-2); font-size:12px; margin:2px 0 12px; }
  .row { display:flex; align-items:center; gap:9px; padding:5px 0; cursor:pointer;
         border:0; background:none; color:inherit; width:100%; text-align:left; font:inherit; }
  .row:hover { color:#fff; }
  .row.off { opacity:.3; }
  .row .name { flex:1; font-size:13px; }
  .row .n { color:var(--ink-2); font-size:12px; font-variant-numeric:tabular-nums; }
  .swatch { width:13px; height:13px; flex:0 0 13px; }
  .seg { display:flex; gap:4px; margin-top:12px; padding-top:12px; border-top:1px solid var(--line); }
  .seg button { flex:1; padding:5px 0; font-size:11px; border:1px solid var(--line);
                background:none; color:var(--ink-2); border-radius:6px; cursor:pointer; }
  .seg button.on { background:#17212e; color:#fff; border-color:#35475e; }

  #side { right:16px; top:16px; width:352px; max-height:calc(100vh - 32px); padding:0;
          display:none; overflow:hidden; flex-direction:column; }
  #side header { padding:16px 18px 12px; border-bottom:1px solid var(--line); position:relative; }
  #side .place { font-size:12px; letter-spacing:.09em; text-transform:uppercase;
                 color:var(--accent); }
  #side .count { color:var(--ink-2); font-size:12px; margin-top:2px; }
  #side .close { position:absolute; top:12px; right:14px; cursor:pointer; color:var(--ink-2);
                 background:none; border:0; font-size:20px; line-height:1; }
  #list { overflow-y:auto; flex:1; }
  .item { display:flex; gap:10px; align-items:flex-start; padding:10px 18px; cursor:pointer;
          border:0; background:none; color:inherit; width:100%; text-align:left; font:inherit;
          border-bottom:1px solid rgba(40,50,63,.5); }
  .item:hover { background:rgba(127,178,240,.07); }
  .item.on { background:rgba(127,178,240,.13); }
  .item .dot { margin-top:4px; flex:0 0 12px; }
  .item .t { font-size:13px; line-height:1.35; }
  .item .g { font-size:11px; color:var(--ink-3); margin-top:2px; }
  #player { padding:14px 18px; border-top:1px solid var(--line); display:none; }
  #player .meta { color:var(--ink-2); font-size:12px; }
  #player audio { width:100%; margin-top:8px; }
  #player a { color:var(--accent); }
  .chip { display:inline-block; font-size:11px; padding:2px 8px; border-radius:99px;
          border:1px solid var(--line); color:var(--ink-2); margin-top:8px; }

  #hint { left:16px; bottom:16px; padding:9px 13px; color:var(--ink-2); font-size:12px; }
  .cluster { cursor:pointer; display:block; transition:transform .13s ease; }
  .cluster:hover { transform:scale(1.15); }
  .cluster.active .halo { opacity:1; }
  .clabel { position:absolute; left:50%; transform:translateX(-50%); top:100%; margin-top:3px;
            font-size:11px; color:#e8edf4; white-space:nowrap; pointer-events:none;
            text-shadow:0 1px 3px #000, 0 0 8px #000; }
  .wrap { position:relative; }
</style>
</head>
<body>
<div id="globe"></div>

<div class="card" id="legend">
  <h1>Sawt</h1>
  <div class="sub"><span id="shown">0</span> recordings in <span id="places">0</span> places</div>
  <div id="rows"></div>
  <div class="seg" id="skins">
    <button data-skin="dark" class="on">Muted</button>
    <button data-skin="marble">Daylight</button>
    <button data-skin="night">Night</button>
  </div>
</div>

<div class="card" id="side">
  <header>
    <button class="close" id="close" aria-label="Close">&times;</button>
    <div class="place" id="s-place"></div>
    <div class="count" id="s-count"></div>
  </header>
  <div id="list"></div>
  <div id="player">
    <div class="meta" id="p-meta"></div>
    <audio id="p-audio" controls preload="auto"></audio>
    <div class="meta" style="margin-top:8px">
      <a id="p-link" target="_blank" rel="noopener">Source page</a>
      <span id="p-coords" style="margin-left:8px"></span>
    </div>
    <div class="meta" id="p-host" style="margin-top:4px"></div>
    <span class="chip" id="p-basis"></span>
  </div>
</div>

<div class="card" id="hint">Drag to spin &middot; scroll to zoom &middot; click a place to open it</div>

<script src="https://unpkg.com/globe.gl@2"></script>
<script>
const POINTS = __POINTS__;
const CLUSTERS = __CLUSTERS__;
const LEGEND = __LEGEND__;
const CLUSTER_BY_ID = Object.fromEntries(CLUSTERS.map(c => [c.id, c]));
const hidden = new Set();
let openCluster = null;

const SKINS = {
  dark:   'https://unpkg.com/three-globe/example/img/earth-dark.jpg',
  marble: 'https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg',
  night:  'https://unpkg.com/three-globe/example/img/earth-night.jpg'
};

// One circle per PLACE, sized by how many recordings are there.
// Area, not radius, carries the count: doubling the radius quadruples the ink, so a
// cluster of 4 would look like 16. sqrt keeps the ink honest.
function clusterSVG(group) {
  const n = group.items.length;
  const d = Math.round(16 + 9 * Math.sqrt(n - 1));
  const r = d / 2 - 3;
  const colour = group.colour;
  const label = n > 1 ? `<text x="${d/2}" y="${d/2}" text-anchor="middle"
        dominant-baseline="central" font-size="${Math.min(13, 8 + n / 6)}"
        font-weight="600" fill="#05070a"
        font-family="ui-sans-serif, system-ui">${n}</text>` : '';
  return `<svg class="cluster" width="${d}" height="${d}" viewBox="0 0 ${d} ${d}">
      <circle class="halo" cx="${d/2}" cy="${d/2}" r="${r + 2.5}" fill="none"
              stroke="${colour}" stroke-width="2" opacity="0"/>
      <circle cx="${d/2}" cy="${d/2}" r="${r + .5}" fill="rgba(2,4,8,.85)"/>
      <circle cx="${d/2}" cy="${d/2}" r="${r}" fill="${colour}"
              stroke="rgba(2,4,8,.9)" stroke-width="1.5" opacity="${n > 1 ? .95 : .9}"/>
      ${label}
    </svg>`;
}

function groups() {
  const visible = POINTS.filter(p => !hidden.has(p.genre));
  const byCluster = {};
  visible.forEach(p => (byCluster[p.cluster] ||= []).push(p));
  return Object.entries(byCluster).map(([id, items]) => {
    // A mixed place takes the colour of whatever it mostly holds. The number on the
    // circle and the list inside it carry the detail; the colour is only a hint.
    const tally = {};
    items.forEach(p => tally[p.colour] = (tally[p.colour] || 0) + 1);
    const colour = Object.entries(tally).sort((a, b) => b[1] - a[1])[0][0];
    const meta = CLUSTER_BY_ID[id];
    return { id, items, colour, lat: meta.lat, lng: meta.lng,
             place: meta.place, short: meta.short };
  });
}

const side = document.getElementById('side');
const audio = document.getElementById('p-audio');

function openPlace(group) {
  openCluster = group.id;
  document.getElementById('s-place').textContent = group.place;
  document.getElementById('s-count').textContent =
    group.items.length + (group.items.length === 1 ? ' recording' : ' recordings');
  document.getElementById('list').innerHTML = group.items.map((p, i) => `
    <button class="item" data-i="${i}">
      <svg class="dot" width="12" height="12" viewBox="0 0 12 12">
        <circle cx="6" cy="6" r="4" fill="${p.style === 'hollow' ? 'none' : p.colour}"
                stroke="${p.colour}" stroke-width="${p.style === 'hollow' ? 2.5 : 1.5}"/>
      </svg>
      <span><span class="t">${p.title}</span><span class="g">${p.genreLabel}</span></span>
    </button>`).join('');
  document.querySelectorAll('#list .item').forEach(el => {
    el.onclick = () => {
      document.querySelectorAll('#list .item').forEach(x => x.classList.remove('on'));
      el.classList.add('on');
      play(group.items[+el.dataset.i]);
    };
  });
  side.style.display = 'flex';
  document.getElementById('player').style.display = 'none';
  audio.pause();

  globe.controls().autoRotate = false;
  globe.pointOfView({ lat: group.lat, lng: group.lng, altitude: 1.4 }, 850);

  // One recording in a place: no reason to make anyone click twice.
  if (group.items.length === 1) {
    document.querySelector('#list .item').classList.add('on');
    play(group.items[0]);
  }
  render();
}

function play(p) {
  const bits = [p.source, 'Tier ' + p.tier, p.license];
  if (p.attribution) bits.push('by ' + p.attribution);
  document.getElementById('p-meta').textContent = bits.filter(Boolean).join(' · ');
  document.getElementById('p-link').href = p.url;
  document.getElementById('p-coords').textContent =
    `${p.lat.toFixed(3)}, ${p.lng.toFixed(3)}` + (p.proximity ? ` · ${p.proximity}` : '');
  document.getElementById('p-host').textContent =
    p.selfHosted ? 'self-hosted copy' : 'streaming from source (not yet self-hosted)';
  document.getElementById('p-host').style.color = p.selfHosted ? '#9daaba' : '#d95926';
  document.getElementById('p-basis').textContent = {
    geotag: 'Located by geotag',
    title: 'Location inferred from the title, city centre only',
    tradition: 'Placed by tradition, not by where it was recorded'
  }[p.basis] || p.basis;
  document.getElementById('player').style.display = 'block';
  if (!p.audio) { audio.removeAttribute('src'); return; }
  audio.src = p.audio;
  // The click is the user gesture browsers require before audio may start. play()
  // still returns a promise that can reject on a dead link or an unsupported codec,
  // and an unhandled rejection is a bare console error with no context.
  audio.play().catch(err => {
    document.getElementById('p-meta').textContent += `  ·  could not play (${err.name})`;
  });
}

document.getElementById('close').onclick = () => {
  side.style.display = 'none'; audio.pause(); openCluster = null; render();
};

const globe = Globe()
  .globeImageUrl(SKINS.dark)
  .bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png')
  .backgroundImageUrl('https://unpkg.com/three-globe/example/img/night-sky.png')
  .atmosphereColor('#79a9e0')
  .atmosphereAltitude(0.15)
  .htmlLat('lat').htmlLng('lng').htmlAltitude(0.01)
  .htmlElement(group => {
    const wrap = document.createElement('div');
    wrap.className = 'wrap';
    wrap.innerHTML = clusterSVG(group)
      + (group.items.length >= 3 ? `<div class="clabel">${group.short}</div>` : '');
    wrap.style.pointerEvents = 'auto';
    wrap.title = `${group.place} — ${group.items.length}`;
    if (group.id === openCluster) wrap.querySelector('.cluster').classList.add('active');
    wrap.onclick = (e) => { e.stopPropagation(); openPlace(group); };
    return wrap;
  })
  (document.getElementById('globe'));

const renderer = globe.renderer();
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
const maxAniso = renderer.capabilities.getMaxAnisotropy();
function sharpen() {
  const m = globe.globeMaterial();
  if (m && m.map) { m.map.anisotropy = maxAniso; m.map.needsUpdate = true; }
  if (m) { m.bumpScale = 4; m.needsUpdate = true; }
}
setTimeout(sharpen, 400);

// The basemap is a single 2048-pixel-wide image wrapped round the sphere, so one
// texture pixel is about 20km at the equator. Past a certain zoom there is simply no
// more detail to show and it turns to mush. Stopping the camera before that point is
// the fix: the globe stays a globe, and the list panel does the close-up work.
globe.controls().minDistance = 165;
globe.controls().maxDistance = 600;
globe.controls().zoomSpeed = 0.75;
globe.controls().enableDamping = true;
globe.controls().dampingFactor = 0.09;

if (globe.htmlElementVisibilityModifier) {
  globe.htmlElementVisibilityModifier((el, isVisible) => {
    el.style.opacity = isVisible ? 1 : 0;
    el.style.pointerEvents = isVisible ? 'auto' : 'none';
  });
}

globe.controls().autoRotate = true;
globe.controls().autoRotateSpeed = 0.3;
globe.pointOfView({ lat: 26, lng: 34, altitude: 2.2 });
globe.controls().addEventListener('start', () => { globe.controls().autoRotate = false; });

document.querySelectorAll('#skins button').forEach(button => {
  button.onclick = () => {
    document.querySelectorAll('#skins button').forEach(b => b.classList.remove('on'));
    button.classList.add('on');
    globe.globeImageUrl(SKINS[button.dataset.skin]);
    setTimeout(sharpen, 400);
  };
});

function render() {
  const g = groups();
  globe.htmlElementsData(g);
  document.getElementById('shown').textContent = g.reduce((n, x) => n + x.items.length, 0);
  document.getElementById('places').textContent = g.length;
  document.querySelectorAll('.row').forEach(row =>
    row.classList.toggle('off', hidden.has(row.dataset.genre)));
}

document.getElementById('rows').innerHTML = LEGEND.map(row => {
  const fill = row.style === 'hollow' ? 'none' : row.colour;
  return `<button class="row" data-genre="${row.genre}">
      <svg class="swatch" viewBox="0 0 14 14" width="13" height="13">
        <circle cx="7" cy="7" r="5" fill="${fill}" stroke="${row.colour}"
                stroke-width="${row.style === 'hollow' ? 2.5 : 1.5}"/>
      </svg>
      <span class="name">${row.label}</span><span class="n">${row.count}</span>
    </button>`;
}).join('');

document.querySelectorAll('.row').forEach(row => {
  row.onclick = () => {
    const g = row.dataset.genre;
    hidden.has(g) ? hidden.delete(g) : hidden.add(g);
    render();
  };
});

render();
function resize() { globe.width(window.innerWidth).height(window.innerHeight); }
window.addEventListener('resize', resize);
resize();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
