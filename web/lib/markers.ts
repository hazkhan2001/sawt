// Globe markers, built as plain DOM elements.
//
// globe.gl's HTML layer asks for a real DOM node per point, not a React component,
// so this file builds SVG as strings. Keeping it out of SawtGlobe.tsx means the
// component describes WHAT is on screen and this file describes HOW one marker looks.

import type { Family, Glyph, PlaceBasis, SoundHub } from "./types";
import { FAMILY_HEX, FAMILY_LABEL, PLACE_BASIS_SHORT } from "./types";

// Everything a marker needs to know, computed once per render in SawtGlobe.
export interface HubView extends SoundHub {
  visibleCount: number;
  families: [Family, number][];      // sorted, largest first
  glyph: Glyph | null;               // set only when every visible track shares one
  basisMix: Partial<Record<PlaceBasis, number>>;
  best: PlaceBasis | null;           // the strongest place evidence this hub holds
  selected: boolean;
  callingNow: string | null;         // "Maghrib" if a prayer began here minutes ago
  nextPrayer: string | null;         // "Maghrib in 23 min", live mode only
}

// Text going into innerHTML must be escaped. A hub named "Tom & Jerry's" would
// otherwise be parsed as markup. It is a small habit that closes a whole class of
// bugs (and, with user-supplied text, a class of security holes).
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]!);
}

// Circle AREA, not radius, encodes count (spec 11): radius grows with the square
// root, so a hub with four recordings looks twice as wide, not four times.
export const discSize = (n: number) => Math.round(16 + 9 * Math.sqrt(Math.max(n - 1, 0)));

/** An SVG donut ring split by family. The dash trick explained inside. */
function donut(cx: number, r: number, width: number, families: [Family, number][]): string {
  // A circle's stroke can be drawn as dashes. Give a circle of circumference C the
  // pattern "L, C-L" and it draws one arc of length L. dashoffset slides where that
  // arc starts. So one circle per family, each offset past the arcs before it, adds
  // up to a pie ring with no path maths at all.
  const C = 2 * Math.PI * r;
  const total = families.reduce((sum, [, n]) => sum + n, 0);
  let offset = 0;
  let svg = "";
  for (const [family, n] of families) {
    const len = (n / total) * C;
    svg +=
      `<circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${FAMILY_HEX[family]}"` +
      ` stroke-width="${width}" stroke-dasharray="${len} ${C - len}"` +
      // -C/4 starts the first arc at twelve o'clock rather than three.
      ` stroke-dashoffset="${-offset + C / 4}" />`;
    offset += len;
  }
  return svg;
}

/** The glyph for a single-family hub: disc, hollow ring or diamond. */
function glyphShape(cx: number, r: number, glyph: Glyph, colour: string): string {
  if (glyph === "diamond") {
    const d = r * 1.15;
    return `<path d="M${cx} ${cx - d} L${cx + d} ${cx} L${cx} ${cx + d} L${cx - d} ${cx} Z"` +
      ` fill="${colour}" stroke="rgba(2,4,8,.9)" stroke-width="1.5" />`;
  }
  if (glyph === "ring") {
    return `<circle cx="${cx}" cy="${cx}" r="${r - 1.5}" fill="rgba(11,16,23,.85)"` +
      ` stroke="${colour}" stroke-width="3" />`;
  }
  return `<circle cx="${cx}" cy="${cx}" r="${r}" fill="${colour}"` +
    ` stroke="rgba(2,4,8,.9)" stroke-width="1.5" />`;
}

export function markerSvg(d: HubView): { svg: string; box: number } {
  const n = d.visibleCount;
  const size = n ? discSize(n) : 12;
  const PAD = 9;                         // room for the certainty ring and anchor ring
  const box = size + PAD * 2;
  const c = box / 2;
  const r = size / 2 - 1.5;
  let body = "";

  // 1. Certainty halo, drawn FIRST so it sits underneath. "Placed by tradition" is
  //    a soft glow with no edge, because the claim itself has no edge: a tradition
  //    belongs to a region, not a street corner.
  if (n && d.best === "tradition") {
    const colour = FAMILY_HEX[d.families[0][0]];
    body += `<circle cx="${c}" cy="${c}" r="${r + 6}" fill="${colour}" opacity=".45"` +
      ` style="filter: blur(3.5px)" />`;
  }

  // 2. The body: empty anchor, one family, or a mixed donut.
  if (!n) {
    body += `<circle cx="${c}" cy="${c}" r="3" fill="#97a4b5" />`;
  } else if (d.families.length === 1) {
    body += glyphShape(c, r, d.glyph ?? "disc", FAMILY_HEX[d.families[0][0]]);
  } else {
    // Mixed: dark centre, ring split by family. The count stays readable in the
    // middle and the ring answers "what is in here?" before anyone clicks.
    body += `<circle cx="${c}" cy="${c}" r="${r}" fill="#0b1017" stroke="rgba(2,4,8,.9)" stroke-width="1" />`;
    body += donut(c, r - 2.25, 4.5, d.families);
  }

  // 3. "Guessed from the title": a dashed outline. Dashes read as "provisional"
  //    in every drawing convention, which is exactly the claim.
  if (n && d.best === "title") {
    body += `<circle cx="${c}" cy="${c}" r="${r + 3.5}" fill="none" stroke="#f2f5f8"` +
      ` stroke-opacity=".85" stroke-width="1.2" stroke-dasharray="2.5 2.5" />`;
  }

  // 4. Anchors: a thin solid ring, the editorial spine. Solid, never dashed, so an
  //    empty anchor can no longer be mistaken for a loading spinner.
  if (d.isAnchor) {
    body += `<circle cx="${c}" cy="${c}" r="${r + (n ? 7 : 4)}" fill="none" stroke="#f2f5f8"` +
      ` stroke-opacity="${n ? 0.55 : 0.8}" stroke-width="1" />`;
  }

  // 5. The count. White on a donut's dark centre, near-black on a filled disc.
  if (n > 1) {
    const ink = d.families.length > 1 || d.glyph === "ring" ? "#f2f5f8" : "#05070a";
    body += `<text x="${c}" y="${c}" text-anchor="middle" dominant-baseline="central"` +
      ` font-size="11" font-weight="600" fill="${ink}">${n}</text>`;
  }

  return { svg: `<svg width="${box}" height="${box}" viewBox="0 0 ${box} ${box}">${body}</svg>`, box };
}

export function tooltipHtml(d: HubView): string {
  const n = d.visibleCount;
  const lines: string[] = [];
  if (!n) {
    lines.push(`<b>${escapeHtml(d.name)}</b> · no openly licensed recordings yet`);
    lines.push(d.isAnchor ? "Anchor hub · click to read the essay" : "");
  } else {
    lines.push(`<b>${escapeHtml(d.name)}</b> · ${n} ${n === 1 ? "recording" : "recordings"}`);
    lines.push(d.families.map(([f, k]) =>
      `<span style="color:${FAMILY_HEX[f]}">●</span> ${FAMILY_LABEL[f]} ${k}`).join("&ensp;"));
    // Spell the certainty mix out: the marker shows only the strongest evidence.
    lines.push(Object.entries(d.basisMix)
      .map(([basis, k]) => `${PLACE_BASIS_SHORT[basis as PlaceBasis]}${n > 1 ? " " + k : ""}`)
      .join(" · "));
  }
  if (d.callingNow) lines.push(`<span style="color:#7fb2f0">${d.callingNow} is being called here now</span>`);
  else if (d.nextPrayer) lines.push(`<span style="color:#7fb2f0">${d.nextPrayer}</span>`);
  return lines.filter(Boolean).map((l) => `<div>${l}</div>`).join("");
}

/** The whole marker element: svg + always-on anchor label + hover tooltip. */
export function buildMarker(d: HubView, onOpen: (hub: HubView) => void): HTMLElement {
  const { svg, box } = markerSvg(d);
  const wrap = document.createElement("div");
  wrap.className = "hub" + (d.selected ? " selected" : "") + (d.callingNow ? " calling" : "") +
    (d.isAnchor ? " anchor" : "");
  wrap.style.width = wrap.style.height = box + "px";
  wrap.style.setProperty("--ring", (box - 14) + "px");
  // The globe's HTML layer sets pointer-events: none on its container, so dragging
  // still works through the markers. Each marker has to opt back in.
  wrap.style.pointerEvents = "auto";
  wrap.setAttribute("role", "button");
  wrap.setAttribute("aria-label", `${d.name}, ${d.visibleCount} recordings`);
  wrap.innerHTML = svg +
    // The label and tooltip are positioned absolutely, so they add nothing to the
    // wrapper's box. globe.gl centres the BOX on the coordinate; a label inside the
    // normal flow would make the box taller and push the dot off its city.
    (d.isAnchor ? `<span class="hub-label">${escapeHtml(d.name)}</span>` : "") +
    `<div class="hub-tip">${tooltipHtml(d)}</div>`;
  wrap.onclick = (event) => { event.stopPropagation(); onOpen(d); };
  return wrap;
}
