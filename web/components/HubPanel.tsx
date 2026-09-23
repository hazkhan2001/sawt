"use client";

// The side card (a bottom sheet on a phone) for one place.
//
// Two clearly separate sections now: "About <place>" for the essay and "Recordings
// (n)" for the tracks. Before, the list sat under a lone "HISTORY" toggle and read
// as if the recordings were part of the essay.

import { useEffect, useRef } from "react";
import type { SoundHub, SoundTrack } from "@/lib/types";
import { GENRE_LABEL, PLACE_BASIS_LABEL } from "@/lib/types";
import { dateLabel, formatDuration } from "@/lib/data";
import { CertaintyIcon, GenreGlyph } from "./Icons";

interface Props {
  hub: SoundHub;
  tracks: SoundTrack[];            // the visible tracks at this place, in list order
  playingId: string | null;
  aboutOpen: boolean;
  prayerNote: string | null;       // live mode: "Maghrib is being called here now"
  onToggleAbout: () => void;
  onPlay: (track: SoundTrack) => void;
  onClose: () => void;
}

export default function HubPanel({ hub, tracks, playingId, aboutOpen, prayerNote,
                                   onToggleAbout, onPlay, onClose }: Props) {
  const activeRow = useRef<HTMLLIElement>(null);

  // Keep the playing row in view when autoplay moves on to the next one.
  // block: "nearest" scrolls only if the row is actually out of sight.
  useEffect(() => {
    activeRow.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [playingId]);

  return (
    <aside className="fixed inset-x-0 z-40 flex flex-col overflow-hidden rounded-t-2xl
                      border border-[var(--color-line)] bg-[var(--color-panel)] shadow-2xl
                      bottom-[var(--player-h)] max-h-[calc(75dvh-var(--player-h))]
                      sm:absolute sm:inset-x-auto sm:bottom-auto sm:right-4 sm:top-4
                      sm:max-h-[calc(100dvh-2rem)] sm:w-[22rem] sm:rounded-xl"
           aria-label={`${hub.name}: place details`}>
      <div className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-[var(--color-line)] sm:hidden" />
      <header className="relative border-b border-[var(--color-line)] px-5 py-4">
        <button onClick={onClose} aria-label="Close"
                className="absolute right-4 top-3 text-xl leading-none text-[var(--color-ink-2)] hover:text-white">
          &times;
        </button>
        <p className="text-xs uppercase tracking-[0.09em] text-[var(--color-accent)]">
          {hub.country}{hub.isAnchor ? " · anchor hub" : ""}
        </p>
        <h2 dir="auto" className="text-base font-semibold">{hub.name}</h2>
        {hub.description ? (
          <p className="mt-1.5 pr-4 text-[13px] leading-relaxed text-[var(--color-ink-2)]">
            {hub.description}
          </p>
        ) : null}
        {prayerNote && <p className="mt-1.5 text-[12px] text-[var(--color-accent)]">{prayerNote}</p>}
      </header>

      {/* One scroll container for the essay AND the list, so a long essay can never
          push the recordings out of reach on a phone. */}
      <div className="flex-1 overflow-y-auto">
        {hub.historicalContext ? (
          <section className="border-b border-[var(--color-line)]">
            <button onClick={onToggleAbout} aria-expanded={aboutOpen}
                    className="flex w-full items-center gap-2 px-5 py-2.5 text-left text-[11px]
                               uppercase tracking-[0.09em] text-[var(--color-ink-2)] hover:text-[var(--color-ink)]">
              <span className="flex-1">About {hub.name}</span>
              <span className={"transition-transform " + (aboutOpen ? "rotate-180" : "")}>&#9662;</span>
            </button>
            {aboutOpen && (
              <div className="space-y-2.5 px-5 pb-4 text-[13px] leading-relaxed text-[var(--color-ink-2)]">
                {/* Paragraph breaks are stored as blank lines; JSX would collapse them. */}
                {hub.historicalContext.split("\n\n").map((para, i) => (
                  <p key={i} dir="auto">{para}</p>
                ))}
              </div>
            )}
          </section>
        ) : hub.isAnchor ? (
          <p className="border-b border-[var(--color-line)] px-5 py-3 text-xs italic text-[var(--color-ink-2)]">
            The written history for this place is still to come.
          </p>
        ) : null}

        <section aria-label="Recordings">
          <h3 className="px-5 pb-1.5 pt-3 text-[11px] uppercase tracking-[0.09em] text-[var(--color-ink-2)]">
            Recordings ({tracks.length})
          </h3>
          <ul>
            {tracks.length === 0 && (
              <li className="px-5 pb-6 pt-1 text-[13px] leading-relaxed text-[var(--color-ink-2)]">
                No openly licensed recordings yet. The open archives hold almost nothing
                from this place, which is itself worth knowing.
              </li>
            )}
            {tracks.map((track) => {
              const active = playingId === track.id;
              return (
                <li key={track.id} ref={active ? activeRow : undefined}
                    className={"border-b border-[var(--color-line)]/50" +
                               (active ? " bg-[var(--color-accent)]/15" : "")}>
                  <button onClick={() => onPlay(track)} aria-current={active}
                          className="flex w-full items-start gap-3 px-5 py-3 text-left hover:bg-[var(--color-accent)]/10">
                    <span className="mt-1"><GenreGlyph genre={track.genre} size={12} /></span>
                    <span className="min-w-0 flex-1">
                      <span dir="auto" className="block text-[13px] leading-snug">{track.displayTitle}</span>
                      <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--color-ink-2)]">
                        <CertaintyIcon basis={track.placeBasis} size={12} />
                        <span>
                          {[GENRE_LABEL[track.genre], dateLabel(track), formatDuration(track.durationSeconds)]
                            .filter(Boolean).join(" · ")}
                        </span>
                      </span>
                    </span>
                  </button>

                  {/* The active row opens up to show provenance: who, what licence,
                      how sure we are of the place, and the raw title as filed. */}
                  {active && (
                    <div className="space-y-1 px-5 pb-3 pl-[2.9rem] text-[11px] leading-relaxed text-[var(--color-ink-2)]">
                      {track.performerOrZawiya && <p dir="auto">{track.performerOrZawiya}</p>}
                      {track.contextNotes && <p dir="auto">{track.contextNotes}</p>}
                      <p>{PLACE_BASIS_LABEL[track.placeBasis]}
                        {track.dateBasis === "unknown" ? " · no recording date known" : ""}</p>
                      {track.title !== track.displayTitle && (
                        <p dir="auto" className="break-all opacity-80">Filed as “{track.title}”</p>
                      )}
                      <p>
                        {[track.license, track.attribution ? "by " + track.attribution : null]
                          .filter(Boolean).join(" · ")}
                        {" · "}
                        <a href={track.sourceUrl} target="_blank" rel="noopener noreferrer"
                           className="text-[var(--color-accent)]">Source page</a>
                      </p>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </aside>
  );
}
