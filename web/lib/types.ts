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
  title: string;          // raw, exactly as the source has it: evidence, never edited
  displayTitle: string;   // derived from title in build_site_data.py, for reading
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
  // Optional in the data today, planned in the spec. Declared so search can read it
  // the day the pipeline starts filling it, with no change here.
  mode?: { system: string; name: string };
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

// ---------------------------------------------------------------------------
// Visual encoding. Colour carries the FAMILY, the glyph carries the GENRE.
//
// Three hues, because a point map is an "all-pairs" form where any colour can sit
// beside any other, and only three survive colour-blind separation at that
// constraint (spec 11). Within a family the glyph separates genres: filled disc,
// hollow ring, or diamond. The rule this file now enforces is that NO TWO GENRES
// SHARE BOTH a colour and a glyph. "other" and "ambience" used to: both grey discs.
// ---------------------------------------------------------------------------

export type Family = "call" | "devotional" | "music" | "recitation" | "neutral";
export type Glyph = "disc" | "ring" | "diamond";

export const FAMILY: Record<Genre, Family> = {
  adhan: "call",
  dhikr_hadra: "devotional", inshad_madih: "devotional", qawwali: "devotional",
  art_music: "music", nawbah: "music",
  tilawa: "recitation",
  ambience: "neutral", other: "neutral",
};

export const GLYPH: Record<Genre, Glyph> = {
  adhan: "disc",
  dhikr_hadra: "disc", inshad_madih: "ring", qawwali: "diamond",
  art_music: "disc", nawbah: "ring",
  tilawa: "ring",
  ambience: "disc", other: "ring",
};

// Plain hex rather than CSS variables, because these get written into SVG strings
// for the globe markers, where a CSS variable would not resolve.
export const FAMILY_HEX: Record<Family, string> = {
  call: "#3987e5",
  devotional: "#d95926",
  music: "#199e70",
  recitation: "#e8eaed",
  neutral: "#8b97a6",
};

export const FAMILY_LABEL: Record<Family, string> = {
  call: "Call to prayer",
  devotional: "Devotional",
  music: "Art music",
  recitation: "Recitation",
  neutral: "Ambience and other",
};

export const genreHex = (g: Genre) => FAMILY_HEX[FAMILY[g]];

export const GENRE_LABEL: Record<Genre, string> = {
  adhan: "Adhan and call to prayer",
  dhikr_hadra: "Sufi dhikr and hadra",
  inshad_madih: "Nasheed, ilahi and madih",
  qawwali: "Qawwali",
  art_music: "Maqam, mugham and modal",
  nawbah: "Andalusi nawbah",
  tilawa: "Quran recitation",
  ambience: "Mosque and street ambience",
  other: "Other",
};

// Certainty about PLACE. Three kinds, never flattened (spec 5).
export const PLACE_BASIS_LABEL: Record<PlaceBasis, string> = {
  geotag: "Located by geotag",
  title: "Location inferred from the title, city centre only",
  tradition: "Placed by tradition, not by where it was recorded",
};

// The short forms, for the legend and tooltips.
export const PLACE_BASIS_SHORT: Record<PlaceBasis, string> = {
  geotag: "Geotagged by the recordist",
  title: "Guessed from the title",
  tradition: "Placed by tradition",
};

// Ordered from most to least certain. The ORDER is data: markers use it to pick the
// strongest evidence a place holds (see lib/markers.ts).
export const PLACE_BASIS_ORDER: PlaceBasis[] = ["geotag", "title", "tradition"];
