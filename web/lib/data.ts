import type { SoundHub, SoundTrack } from "./types";
import hubsJson from "@/public/data/hubs.json";
import tracksJson from "@/public/data/tracks.json";

// Importing the JSON directly means Next bundles it at build time: no fetch, no
// loading state, no network request when someone opens the page. That works because
// the data only changes when the Python pipeline runs and the site is rebuilt.
// The `as` casts are the one place we assert the JSON matches the types; everything
// downstream is checked by the compiler.
export const hubs = hubsJson as SoundHub[];
export const tracks = tracksJson as SoundTrack[];

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || !isFinite(seconds)) return "";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

// "undated" is written out on purpose. A blank where the year should be looks like
// a layout gap; the word says it is a gap in what we know. 66 of 101 tracks say it.
export function dateLabel(track: SoundTrack): string {
  if (track.yearRange) return `${track.yearRange[0]}–${track.yearRange[1]}`;
  if (track.recordedYear) return String(track.recordedYear);
  return "undated";
}
