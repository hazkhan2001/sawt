// The TypeScript half of the contract.
//
// These types mirror the pydantic models in build_site_data.py. Python validates the
// data on the way out; TypeScript checks that this app reads it correctly on the way
// in. Neither one can verify the other, so when a field changes it has to change in
// both places, and the spec's section 5 is the single description they both follow.

export type Genre =
  | "art_music" | "qawwali" | "dhikr_hadra" | "inshad_madih"
  | "nawbah" | "adhan" | "tilawa" | "ambience" | "other";

export type RightsBasis =
  | "cc0" | "cc-by" | "cc-by-sa" | "pdm"
  | "pd-us-published-pre-cutoff" | "own_recording" | "permission" | "stream_only";

// How much we actually know about where and when. The UI must not present an
// inference with the same confidence as a fact.
export type PlaceBasis = "geotag" | "title" | "tradition";
export type DateBasis = "stated" | "catalogue" | "estimated" | "unknown";

export interface SoundTrack {
  id: string;
  hubId: string;
  title: string;
  performerOrZawiya: string;
  genre: Genre;
  subGenre: string;
  instrumentation: string[];
  audioUrl: string;
  archivalUrl: string | null;
  durationSeconds: number | null;
  recordedYear: number | null;
  yearRange: [number, number] | null;
  dateBasis: DateBasis;
  placeBasis: PlaceBasis;
  lat: number;
  lng: number;
  rightsBasis: RightsBasis;
  license: string;
  attribution: string | null;
  sourceUrl: string;
  contextNotes: string;
}

export interface SoundHub {
  id: string;
  name: string;
  country: string;
  lat: number;
  lng: number;
  description: string;
  historicalContext: string;
  isAnchor: boolean;
  trackCount: number;
}

// Colour carries the family, shape carries the genre. Three hues, because a point
// map is an "all-pairs" form where any colour can sit beside any other, and only
// three survive colour-blind separation testing at that constraint. See spec 11.
export const FAMILY_COLOUR: Record<Genre, string> = {
  adhan: "var(--color-call)",
  dhikr_hadra: "var(--color-devotional)",
  inshad_madih: "var(--color-devotional)",
  qawwali: "var(--color-devotional)",
  art_music: "var(--color-music)",
  nawbah: "var(--color-music)",
  tilawa: "var(--color-recitation)",
  ambience: "var(--color-muted)",
  other: "var(--color-muted)",
};

export const HOLLOW: Genre[] = ["inshad_madih", "qawwali", "tilawa"];

export const PLACE_BASIS_LABEL: Record<PlaceBasis, string> = {
  geotag: "Located by geotag",
  title: "Location inferred from the title, city centre only",
  tradition: "Placed by tradition, not by where it was recorded",
};
