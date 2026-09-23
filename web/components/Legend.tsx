"use client";

// The legend card: search, genre filters, the certainty key, and the layer toggles.
// Every genre row is a filter (spec 11), so identity never rests on colour alone.

import { useMemo, useState } from "react";
import type { Genre, PlaceBasis } from "@/lib/types";
import { GENRE_LABEL, PLACE_BASIS_SHORT, PLACE_BASIS_ORDER } from "@/lib/types";
import { search, type SearchHit, type buildIndex } from "@/lib/search";
import { CertaintyIcon, GenreGlyph } from "./Icons";

export type SkinName = "muted" | "daylight" | "night";

interface Props {
  trackCount: number;
  placeCount: number;
  undatedCount: number;
  genreCounts: [Genre, number][];
  hidden: Set<Genre>;
  onToggleGenre: (g: Genre) => void;
  skin: SkinName;
  onSkin: (s: SkinName) => void;
  live: boolean;
  onLive: () => void;
  liveSummary: string | null;
  drifting: boolean;
  onDrift: () => void;
  index: ReturnType<typeof buildIndex>;
  onPick: (hit: SearchHit) => void;
}

const LINE_KEY: [string, string, string][] = [
  // [prayer, colour, dash pattern for the swatch]
  ["Fajr", "#f5c26b", "3 2"],
  ["Dhuhr", "#f2f5f8", ""],
  ["Asr", "#f5c26b", ""],
  ["Maghrib", "#7fb2f0", ""],
  ["Isha", "#7fb2f0", "3 2"],
];

export default function Legend(p: Props) {
  const [open, setOpen] = useState(false);       // phones only; always open from sm up
  const [query, setQuery] = useState("");
  const hits = useMemo(() => search(p.index, query), [p.index, query]);

  return (
    <section className="absolute left-3 top-3 z-20 max-h-[calc(100dvh-var(--player-h)-1.5rem)]
                        max-w-[calc(100vw-1.5rem)] overflow-y-auto rounded-xl border
                        border-[var(--color-line)] bg-[var(--color-panel)] px-3 py-2 shadow-2xl
                        sm:left-4 sm:top-4 sm:max-h-[calc(100dvh-var(--player-h)-3rem)] sm:w-64 sm:px-4 sm:py-4">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
              className="flex w-full items-center gap-2 text-left sm:pointer-events-none">
        <span className="text-base font-semibold tracking-wide sm:text-lg">Sawt</span>
        <span className="flex-1 text-[11px] text-[var(--color-ink-2)] sm:hidden">{p.trackCount} recordings</span>
        <span className={"text-[var(--color-ink-2)] transition-transform sm:hidden " + (open ? "rotate-180" : "")}>&#9662;</span>
      </button>

      <div className={(open ? "block" : "hidden") + " sm:block"}>
        <p className="mb-2 mt-1 text-xs text-[var(--color-ink-2)]">
          {p.trackCount} recordings in {p.placeCount} places
        </p>

        {/* Search */}
        <div className="relative mb-3">
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
                 placeholder="Search places, performers, genres"
                 aria-label="Search places, performers and recordings"
                 className="w-full rounded-md border border-[var(--color-line)] bg-[#070b10] px-2.5 py-1.5
                            text-[12px] placeholder:text-[var(--color-ink-2)]/70 focus:border-[#35475e] focus:outline-none" />
          {query.trim() && (
            <ul className="mt-1 max-h-60 overflow-y-auto rounded-md border border-[var(--color-line)] bg-[#070b10]">
              {hits.length === 0 && (
                <li className="px-2.5 py-2 text-[12px] text-[var(--color-ink-2)]">Nothing matches.</li>
              )}
              {hits.map((hit) => (
                <li key={hit.kind + (hit.track?.id ?? hit.hub.id)}>
                  <button onClick={() => { p.onPick(hit); setQuery(""); setOpen(false); }}
                          className="flex w-full items-start gap-2 px-2.5 py-1.5 text-left hover:bg-white/5">
                    <span className="mt-1">
                      {hit.track ? <GenreGlyph genre={hit.track.genre} size={10} />
                                 : <span className="block h-2.5 w-2.5 rounded-full border border-[var(--color-ink-2)]" />}
                    </span>
                    <span className="min-w-0">
                      <span dir="auto" className="block truncate text-[12px]">{hit.label}</span>
                      <span className="block truncate text-[10.5px] text-[var(--color-ink-2)]">{hit.detail}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Genres: each row is a filter */}
        {p.genreCounts.map(([genre, count]) => (
          <button key={genre} onClick={() => p.onToggleGenre(genre)} aria-pressed={!p.hidden.has(genre)}
                  className={"flex w-full items-center gap-2 py-1 text-left text-[13px] transition-opacity hover:text-white" +
                             (p.hidden.has(genre) ? " opacity-30" : "")}>
            <GenreGlyph genre={genre} />
            <span className="flex-1">{GENRE_LABEL[genre]}</span>
            <span className="text-xs tabular-nums text-[var(--color-ink-2)]">{count}</span>
          </button>
        ))}
        <p className="mt-1 text-[10.5px] leading-snug text-[var(--color-ink-2)]">
          A place holding several kinds shows a ring split by kind.
        </p>

        {/* Certainty key: spec 5, made visible */}
        <h3 className="mt-3 border-t border-[var(--color-line)] pt-3 text-[11px] uppercase tracking-[0.09em] text-[var(--color-ink-2)]">
          How sure are we?
        </h3>
        {PLACE_BASIS_ORDER.map((basis: PlaceBasis) => (
          <div key={basis} className="flex items-center gap-2 py-0.5 text-[12px]">
            <CertaintyIcon basis={basis} />
            <span>{PLACE_BASIS_SHORT[basis]}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 py-0.5 text-[12px]">
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden className="shrink-0">
            <circle cx="8" cy="8" r="3" fill="#97a4b5" />
            <circle cx="8" cy="8" r="6.5" fill="none" stroke="#f2f5f8" strokeOpacity=".7" />
          </svg>
          <span>Anchor hub, with an essay</span>
        </div>
        <p className="mt-1 text-[10.5px] leading-snug text-[var(--color-ink-2)]">
          A marker shows the strongest evidence at that place; each recording is marked in its list.
          {p.undatedCount ? ` ${p.undatedCount} of ${p.trackCount} recordings are undated.` : ""}
        </p>

        {/* Layers and modes */}
        <div className="mt-3 grid grid-cols-2 gap-1 border-t border-[var(--color-line)] pt-3">
          <button onClick={p.onDrift} aria-pressed={p.drifting}
                  className={"rounded-md border py-1.5 text-[12px] transition-colors " +
                             (p.drifting ? "border-[var(--color-accent)] bg-[#17212e] text-white"
                                         : "border-[var(--color-line)] text-[var(--color-ink-2)] hover:text-white")}>
            {p.drifting ? "Drifting…" : "Drift"}
          </button>
          <button onClick={p.onLive} aria-pressed={p.live}
                  className={"rounded-md border py-1.5 text-[12px] transition-colors " +
                             (p.live ? "border-[var(--color-accent)] bg-[#17212e] text-white"
                                     : "border-[var(--color-line)] text-[var(--color-ink-2)] hover:text-white")}>
            Prayer times now
          </button>
        </div>

        {p.live && (
          <div className="mt-2 text-[11px] leading-snug text-[var(--color-ink-2)]">
            {LINE_KEY.map(([name, colour, dash]) => (
              <div key={name} className="flex items-center gap-2 py-0.5">
                <svg width="22" height="6" aria-hidden className="shrink-0">
                  <line x1="1" y1="3" x2="21" y2="3" stroke={colour}
                        strokeWidth={name === "Maghrib" ? 3 : 1.6} strokeDasharray={dash} />
                </svg>
                <span className={name === "Maghrib" ? "text-[var(--color-ink)]" : ""}>{name}</span>
              </div>
            ))}
            <p className="mt-1">
              Each line is where that prayer&rsquo;s time has just arrived. They sweep west about
              one degree every four minutes. Muslim World League angles; Asr by the majority
              reckoning (the Hanafi Asr comes later).
            </p>
            {p.liveSummary && <p className="mt-1 text-[var(--color-accent)]">{p.liveSummary}</p>}
          </div>
        )}

        {/* Basemap. Disabled while the live layer supplies its own day and night. */}
        <div className="mt-3 flex gap-1 border-t border-[var(--color-line)] pt-3">
          {(["muted", "daylight", "night"] as SkinName[]).map((name) => (
            <button key={name} onClick={() => p.onSkin(name)} disabled={p.live}
                    className={"flex-1 rounded-md border border-[var(--color-line)] py-1 text-[11px] capitalize transition-colors disabled:opacity-30 " +
                               (p.skin === name && !p.live ? "border-[#35475e] bg-[#17212e] text-white"
                                                            : "text-[var(--color-ink-2)] hover:text-white")}>
              {name}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
