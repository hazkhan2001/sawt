// Small SVG icons shared by the legend, the list rows and the player.
// The same encodings as the globe markers in lib/markers.ts, drawn as React.

import type { Genre, PlaceBasis } from "@/lib/types";
import { GLYPH, genreHex, PLACE_BASIS_LABEL } from "@/lib/types";

export function GenreGlyph({ genre, size = 13 }: { genre: Genre; size?: number }) {
  const colour = genreHex(genre);
  const glyph = GLYPH[genre];
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" className="shrink-0" aria-hidden>
      {glyph === "diamond" ? (
        <path d="M7 1.5 L12.5 7 L7 12.5 L1.5 7 Z" fill={colour} />
      ) : glyph === "ring" ? (
        <circle cx="7" cy="7" r="4.6" fill="none" stroke={colour} strokeWidth="2.4" />
      ) : (
        <circle cx="7" cy="7" r="5.2" fill={colour} />
      )}
    </svg>
  );
}

// The three kinds of place certainty (spec 5), as the globe draws them:
// a solid dot, a dashed outline, a soft halo.
export function CertaintyIcon({ basis, size = 14 }: { basis: PlaceBasis; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" className="shrink-0"
         role="img" aria-label={PLACE_BASIS_LABEL[basis]}>
      <title>{PLACE_BASIS_LABEL[basis]}</title>
      {basis === "geotag" && <circle cx="8" cy="8" r="4.5" fill="#97a4b5" />}
      {basis === "title" && (
        <>
          <circle cx="8" cy="8" r="3.2" fill="#97a4b5" />
          <circle cx="8" cy="8" r="6.3" fill="none" stroke="#f2f5f8" strokeWidth="1.1"
                  strokeDasharray="2 2" />
        </>
      )}
      {basis === "tradition" && (
        <>
          <circle cx="8" cy="8" r="6.5" fill="#97a4b5" opacity=".35" style={{ filter: "blur(1.6px)" }} />
          <circle cx="8" cy="8" r="3.2" fill="#97a4b5" />
        </>
      )}
    </svg>
  );
}

// Player buttons. Plain paths rather than an icon library: five shapes do not
// justify a dependency.
const PATHS = {
  play: "M6 4.5v11l9-5.5z",
  pause: "M5.5 4.5h3v11h-3zM11.5 4.5h3v11h-3z",
  prev: "M5 4.5h2v11H5zM16 4.5v11l-8-5.5z",
  next: "M13 4.5h2v11h-2zM4 4.5v11l8-5.5z",
  link: "M8.5 11.5l3-3M7 9.5l-1.8 1.8a2.5 2.5 0 003.5 3.5L10.5 13M13 10.5l1.8-1.8a2.5 2.5 0 00-3.5-3.5L9.5 7",
  close: "M5.5 5.5l9 9M14.5 5.5l-9 9",
};

export function Icon({ name, size = 18 }: { name: keyof typeof PATHS; size?: number }) {
  const stroked = name === "link" || name === "close";
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden>
      <path d={PATHS[name]} fill={stroked ? "none" : "currentColor"}
            stroke={stroked ? "currentColor" : "none"} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
