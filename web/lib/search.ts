// Search across places, performers, titles and (once the pipeline fills it) maqam
// names.
//
// The same lesson as the Python side (spec 11): normalise text BEFORE comparing,
// never at display time. "Beyoğlu", "beyoglu" and "BEYOGLU" should all match, and
// so should "Semaisi" typed without the Turkish dotless i.

import type { SoundHub, SoundTrack } from "./types";
import { GENRE_LABEL } from "./types";

export function normalise(text: string): string {
  return text
    .normalize("NFKD")                  // split "ğ" into "g" + a combining breve
    .replace(/[̀-ͯ]/g, "")    // ...then drop the combining marks
    .replace(/[ً-ٰٟ]/g, "") // Arabic short-vowel marks (tashkil)
    .replace(/ı/g, "i")                 // Turkish dotless i has no decomposition
    .toLowerCase();
}

export interface SearchHit {
  kind: "place" | "recording";
  hub: SoundHub;
  track?: SoundTrack;
  label: string;
  detail: string;
}

// Build the searchable text once per item, not once per keystroke.
export function buildIndex(hubs: SoundHub[], tracks: SoundTrack[]) {
  const hubById = new Map(hubs.map((h) => [h.id, h]));
  const places = hubs
    .filter((h) => h.id !== "unplaced")
    .map((hub) => ({ hub, text: normalise(`${hub.name} ${hub.country}`) }));
  const recordings = tracks.map((track) => ({
    track,
    hub: hubById.get(track.hubId)!,
    text: normalise([
      track.displayTitle, track.title, track.performerOrZawiya, track.subGenre,
      GENRE_LABEL[track.genre], track.mode?.name ?? "", track.attribution ?? "",
      track.contextNotes, track.instrumentation.join(" "),
    ].join(" ")),
  }));
  return { places, recordings };
}

export function search(index: ReturnType<typeof buildIndex>, query: string, limit = 12): SearchHit[] {
  // Every word must appear somewhere ("adhan cairo" narrows, rather than widens).
  const words = normalise(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const matches = (text: string) => words.every((w) => text.includes(w));

  const hits: SearchHit[] = [];
  for (const p of index.places) {
    if (matches(p.text)) hits.push({
      kind: "place", hub: p.hub, label: p.hub.name,
      detail: `${p.hub.country}${p.hub.trackCount ? " · " + p.hub.trackCount + " recordings" : " · no recordings yet"}`,
    });
  }
  for (const r of index.recordings) {
    // A recording also matches on its place's name, so "istanbul sufi" works.
    if (matches(r.text + " " + normalise(r.hub.name))) hits.push({
      kind: "recording", hub: r.hub, track: r.track, label: r.track.displayTitle,
      detail: `${r.hub.name} · ${GENRE_LABEL[r.track.genre]}`,
    });
  }
  return hits.slice(0, limit);
}
