"use client";

// "use client" marks this file as a CLIENT component: it ships to the browser and
// runs there. It has to, because a globe is WebGL and WebGL needs a real canvas,
// a GPU and a window. Everything else in this app is a server component that runs
// once at build time and arrives as finished HTML.

import { useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { SoundHub, SoundTrack, Genre } from "@/lib/types";
import { FAMILY_COLOUR, HOLLOW, PLACE_BASIS_LABEL } from "@/lib/types";
import { formatDuration, yearLabel } from "@/lib/data";

// react-globe.gl reaches for `window` the moment it is imported, and during a build
// there is no window. ssr:false loads it only in the browser. Without this the build
// dies with "window is not defined".
const Globe = dynamic(() => import("react-globe.gl"), { ssr: false });

// Real NASA imagery, three ways. Muted is the default because the markers read most
// clearly against it; daylight is the familiar Blue Marble; night is the Black Marble
// city-lights composite.
type SkinName = "muted" | "daylight" | "night";
const SKINS: Record<SkinName, string> = {
  muted: "https://unpkg.com/three-globe/example/img/earth-dark.jpg",
  daylight: "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg",
  night: "https://unpkg.com/three-globe/example/img/earth-night.jpg",
};

// The same three hues as the Python prototype, as plain hex because these get written
// into an SVG string where a CSS variable would not resolve.
const HEX_COLOUR: Record<Genre, string> = {
  adhan: "#3987e5",
  dhikr_hadra: "#d95926",
  inshad_madih: "#d95926",
  qawwali: "#d95926",
  art_music: "#199e70",
  nawbah: "#199e70",
  tilawa: "#e8eaed",
  ambience: "#8b97a6",
  other: "#8b97a6",
};

const GENRE_LABEL: Partial<Record<Genre, string>> = {
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

export default function SawtGlobe({
  hubs, tracks,
}: { hubs: SoundHub[]; tracks: SoundTrack[] }) {
  const [openHub, setOpenHub] = useState<SoundHub | null>(null);
  const [playing, setPlaying] = useState<SoundTrack | null>(null);
  const [hidden, setHidden] = useState<Set<Genre>>(new Set());
  const [skin, setSkin] = useState<SkinName>("muted");
  // The legend starts collapsed. On a phone it opens with a tap; from the sm
  // breakpoint up CSS keeps it open regardless, so this state does nothing there.
  const [legendOpen, setLegendOpen] = useState(false);
  // The hub essay starts collapsed. It runs to roughly two hundred words, and on a
  // phone the panel is capped at 75% of the viewport, so leaving it open by default
  // would push every recording off the bottom of the screen before you saw one.
  const [historyOpen, setHistoryOpen] = useState(false);
  const globeRef = useRef<any>(null);

  // useMemo caches a computed value and recomputes only when its inputs change.
  const visibleTracks = useMemo(
    () => tracks.filter((t) => !hidden.has(t.genre)),
    [tracks, hidden],
  );

  const visibleHubs = useMemo(() => {
    // Each hub needs two things the raw data does not carry: how many of its tracks
    // are visible right now, and what colour to draw. A place holding four adhan and
    // one mugham takes the adhan colour. The number on the circle and the list inside
    // carry the detail, so colour is only a hint at what is mostly there.
    const counts = new Map<string, number>();
    const palettes = new Map<string, Map<string, number>>();
    visibleTracks.forEach((t) => {
      counts.set(t.hubId, (counts.get(t.hubId) ?? 0) + 1);
      const tally = palettes.get(t.hubId) ?? new Map<string, number>();
      const colour = HEX_COLOUR[t.genre];
      tally.set(colour, (tally.get(colour) ?? 0) + 1);
      palettes.set(t.hubId, tally);
    });
    return hubs
      .map((h) => {
        const tally = palettes.get(h.id);
        const colour = tally
          ? [...tally.entries()].sort((a, b) => b[1] - a[1])[0][0]
          : "#8b97a6";
        return { ...h, visibleCount: counts.get(h.id) ?? 0, colour };
      })
      .filter((h) => h.visibleCount > 0 || h.isAnchor);
  }, [hubs, visibleTracks]);

  const genreCounts = useMemo(() => {
    const counts = new Map<Genre, number>();
    tracks.forEach((t) => counts.set(t.genre, (counts.get(t.genre) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [tracks]);

  const openTracks = openHub
    ? visibleTracks.filter((t) => t.hubId === openHub.id)
    : [];

  function openPlace(hub: SoundHub) {
    setOpenHub(hub);
    setPlaying(null);
    setHistoryOpen(false);   // a new place starts closed, whatever the last one was
    globeRef.current?.pointOfView(
      { lat: hub.lat, lng: hub.lng, altitude: 1.4 }, 850,
    );
  }

  function toggleGenre(genre: Genre) {
    setHidden((current) => {
      // React state must never be mutated in place: make a new Set, or React cannot
      // tell anything changed and will not re-render.
      const next = new Set(current);
      if (next.has(genre)) next.delete(genre);
      else next.add(genre);
      return next;
    });
  }

  return (
    <main className="relative h-dvh w-full overflow-hidden">
      {/* The globe lives in its own layer at z-0. Everything else stacks above it.
          Without an explicit layer the markers and the panels share one stacking
          context and their order depends on document order, which is fragile. */}
      <div className="absolute inset-0 z-0">
      <Globe
        ref={globeRef}
        globeImageUrl={SKINS[skin]}
        bumpImageUrl="https://unpkg.com/three-globe/example/img/earth-topology.png"
        backgroundImageUrl="https://unpkg.com/three-globe/example/img/night-sky.png"
        atmosphereColor="#79a9e0"
        atmosphereAltitude={0.15}
        htmlElementsData={visibleHubs}
        htmlLat={(d: any) => d.lat}
        htmlLng={(d: any) => d.lng}
        htmlAltitude={0.01}
        htmlElement={(d: any) => {
          const size = Math.round(16 + 9 * Math.sqrt(Math.max(d.visibleCount - 1, 0)));
          const wrap = document.createElement("div");
          wrap.style.cursor = "pointer";
          // The globe's HTML layer sets pointer-events: none on its container, so that
          // dragging the globe still works through the markers. Each marker has to opt
          // back in. This one line is why nothing responded to a click.
          wrap.style.pointerEvents = "auto";
          wrap.innerHTML =
            '<svg width="' + size + '" height="' + size +
            '" viewBox="0 0 ' + size + ' ' + size + '">' +
            '<circle cx="' + size / 2 + '" cy="' + size / 2 +
            '" r="' + (size / 2 - 2.5) + '" fill="' +
            (d.visibleCount ? d.colour : "none") + '" stroke="' +
            (d.visibleCount ? "rgba(2,4,8,.9)" : "#8b97a6") + '" stroke-width="' +
            (d.visibleCount ? 1.5 : 2) + '" stroke-dasharray="' +
            (d.visibleCount ? "" : "3 3") + '" />' +
            (d.visibleCount > 1
              ? '<text x="' + size / 2 + '" y="' + size / 2 +
                '" text-anchor="middle" dominant-baseline="central" font-size="11"' +
                ' font-weight="600" fill="#05070a">' + d.visibleCount + "</text>"
              : "") +
            "</svg>";
          wrap.title = d.name + " (" + d.visibleCount + ")";
          wrap.onclick = (event) => { event.stopPropagation(); openPlace(d); };
          return wrap;
        }}
        htmlElementVisibilityModifier={(el: HTMLElement, isVisible: boolean) => {
          // Hide markers on the far side of the sphere so the back does not show
          // through the front.
          el.style.opacity = isVisible ? "1" : "0";
          el.style.pointerEvents = isVisible ? "auto" : "none";
        }}
      />
      </div>

      {/* A scrim: darkens the globe behind an open panel, and closes it on a tap.
          On a phone the panel covers most of the screen, so the globe behind it is
          noise. On a wide screen the panel is a side card and the scrim would be
          heavy-handed, so it only appears below the sm breakpoint. */}
      {openHub && (
        <button
          aria-label="Close panel"
          onClick={() => { setOpenHub(null); setPlaying(null); setHistoryOpen(false); }}
          className="fixed inset-0 z-30 bg-black/55 sm:hidden"
        />
      )}

      {/* Legend, filters and basemap */}
      <section className="absolute left-3 top-3 z-20 max-w-[calc(100vw-1.5rem)]
                          rounded-xl border border-[var(--color-line)]
                          bg-[var(--color-panel)] px-3 py-2 shadow-2xl
                          sm:left-4 sm:top-4 sm:w-64 sm:px-4 sm:py-4">
        {/* The header is a button on a phone and plain text on a wider screen. One
            element doing both jobs, rather than two that can drift apart. */}
        <button
          onClick={() => setLegendOpen((open) => !open)}
          className="flex w-full items-center gap-2 text-left sm:pointer-events-none"
          aria-expanded={legendOpen}
        >
          <span className="text-base font-semibold tracking-wide sm:text-lg">Sawt</span>
          <span className="flex-1 text-[11px] text-[var(--color-ink-2)] sm:hidden">
            {visibleTracks.length} recordings
          </span>
          <span className={"text-[var(--color-ink-2)] transition-transform sm:hidden " +
                           (legendOpen ? "rotate-180" : "")}>
            &#9662;
          </span>
        </button>

        <div className={(legendOpen ? "block" : "hidden") + " sm:block"}>
        <p className="mb-2 mt-1 text-xs text-[var(--color-ink-2)] sm:mb-3">
          {visibleTracks.length} recordings in{" "}
          {visibleHubs.filter((h) => h.visibleCount > 0).length} places
        </p>

        {genreCounts.map(([genre, count]) => (
          <button
            key={genre}
            onClick={() => toggleGenre(genre)}
            className={"flex w-full items-center gap-2 py-1 text-left text-[13px]" +
                       " transition-opacity hover:text-white" +
                       (hidden.has(genre) ? " opacity-30" : "")}
          >
            <svg width="13" height="13" viewBox="0 0 14 14" className="shrink-0">
              <circle cx="7" cy="7" r="5"
                fill={HOLLOW.includes(genre) ? "none" : FAMILY_COLOUR[genre]}
                stroke={FAMILY_COLOUR[genre]}
                strokeWidth={HOLLOW.includes(genre) ? 2.5 : 1.5} />
            </svg>
            <span className="flex-1">{GENRE_LABEL[genre] ?? genre}</span>
            <span className="text-xs tabular-nums text-[var(--color-ink-2)]">{count}</span>
          </button>
        ))}

        <div className="mt-3 flex gap-1 border-t border-[var(--color-line)] pt-3">
          {(["muted", "daylight", "night"] as SkinName[]).map((name) => (
            <button
              key={name}
              onClick={() => setSkin(name)}
              className={"flex-1 rounded-md border border-[var(--color-line)] py-1" +
                         " text-[11px] capitalize transition-colors " +
                         (skin === name
                           ? "border-[#35475e] bg-[#17212e] text-white"
                           : "text-[var(--color-ink-2)] hover:text-white")}
            >
              {name}
            </button>
          ))}
        </div>
        </div>
      </section>

      {/* Hub panel */}
      {openHub && (
        // On a phone this is a bottom sheet: full width, anchored to the bottom edge,
        // capped at 75% of the viewport so the globe stays visible above it. From the
        // sm breakpoint up it becomes the floating side card again.
        //
        // The background is now fully OPAQUE. It was 95% with a backdrop blur, which
        // let the bright markers behind it glow through and smear. Translucency is a
        // nice effect over a photograph and a bad one over forty small bright dots.
        <aside className="fixed inset-x-0 bottom-0 z-40 flex max-h-[75dvh] flex-col
                          overflow-hidden rounded-t-2xl border border-[var(--color-line)]
                          bg-[var(--color-panel)] shadow-2xl
                          sm:absolute sm:inset-x-auto sm:bottom-auto sm:right-4 sm:top-4
                          sm:max-h-[calc(100dvh-2rem)] sm:w-[22rem] sm:rounded-xl">
          <div className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full
                          bg-[var(--color-line)] sm:hidden" />
          <header className="relative border-b border-[var(--color-line)] px-5 py-4">
            <button
              onClick={() => { setOpenHub(null); setPlaying(null); setHistoryOpen(false); }}
              className="absolute right-4 top-3 text-xl leading-none text-[var(--color-ink-2)]"
              aria-label="Close"
            >
              &times;
            </button>
            <p className="text-xs uppercase tracking-[0.09em] text-[var(--color-accent)]">
              {openHub.country}
            </p>
            <h2 className="text-base font-semibold">{openHub.name}</h2>
            <p className="mt-1 text-xs text-[var(--color-ink-2)]">
              {openTracks.length} {openTracks.length === 1 ? "recording" : "recordings"}
              {openHub.isAnchor ? " · anchor hub" : ""}
            </p>
            {openHub.description ? (
              <p className="mt-2 pr-4 text-[13px] leading-relaxed text-[var(--color-ink-2)]">
                {openHub.description}
              </p>
            ) : null}
          </header>

          {/* One scroll container for the essay AND the track list. Putting the essay
              in the fixed header instead made the header taller than the sheet on a
              phone, which left no room at all for the recordings it was introducing. */}
          <div className="flex-1 overflow-y-auto">
            {openHub.historicalContext ? (
              <div className="border-b border-[var(--color-line)]">
                <button
                  onClick={() => setHistoryOpen((open) => !open)}
                  aria-expanded={historyOpen}
                  className="flex w-full items-center gap-2 px-5 py-2.5 text-left
                             text-[11px] uppercase tracking-[0.09em]
                             text-[var(--color-ink-2)] hover:text-[var(--color-ink)]"
                >
                  <span className="flex-1">History</span>
                  <span className={"transition-transform " + (historyOpen ? "rotate-180" : "")}>
                    &#9662;
                  </span>
                </button>
                {historyOpen && (
                  <div className="space-y-2.5 px-5 pb-4 text-[13px] leading-relaxed
                                  text-[var(--color-ink-2)]">
                    {/* The essay stores paragraph breaks as blank lines. JSX collapses
                        a newline inside a text node to a space, so the split has to
                        happen here or the whole thing arrives as one grey slab. */}
                    {openHub.historicalContext.split("\n\n").map((para, i) => (
                      <p key={i}>{para}</p>
                    ))}
                  </div>
                )}
              </div>
            ) : openHub.isAnchor ? (
              <p className="border-b border-[var(--color-line)] px-5 py-3 text-xs
                            italic text-[var(--color-ink-2)]">
                The written history for this place is still to come.
              </p>
            ) : null}

          <ul>
            {openTracks.length === 0 && (
              <li className="px-5 py-6 text-[13px] text-[var(--color-ink-2)]">
                Nothing here yet. The open archives hold almost nothing from this place,
                which is itself worth knowing.
              </li>
            )}
            {openTracks.map((track) => (
              <li key={track.id}>
                <button
                  onClick={() => setPlaying(track)}
                  className={"flex w-full items-start gap-3 border-b" +
                             " border-[var(--color-line)]/50 px-5 py-3 text-left" +
                             " hover:bg-[var(--color-accent)]/10" +
                             (playing?.id === track.id ? " bg-[var(--color-accent)]/15" : "")}
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" className="mt-1.5 shrink-0">
                    <circle cx="6" cy="6" r="4"
                      fill={HOLLOW.includes(track.genre) ? "none" : FAMILY_COLOUR[track.genre]}
                      stroke={FAMILY_COLOUR[track.genre]}
                      strokeWidth={HOLLOW.includes(track.genre) ? 2.5 : 1.5} />
                  </svg>
                  <span>
                    <span className="block text-[13px] leading-snug">{track.title}</span>
                    <span className="mt-0.5 block text-[11px] text-[var(--color-ink-2)]">
                      {[GENRE_LABEL[track.genre], yearLabel(track),
                        formatDuration(track.durationSeconds)]
                        .filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          </div>

          {playing && (
            <footer className="border-t border-[var(--color-line)] px-5 py-4">
              {/* A plain <audio> element. Phase 3 replaces this with Howler for
                  crossfades; for now the browser's own player is the right amount of
                  machinery, and it is accessible and keyboard-operable for free. */}
              <audio key={playing.id} src={"/" + playing.audioUrl} controls autoPlay
                     className="w-full" />
              <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-ink-2)]">
                {[playing.license,
                  playing.attribution ? "by " + playing.attribution : null]
                  .filter(Boolean).join(" · ")}
              </p>
              {playing.contextNotes && (
                <p className="mt-1 text-[11px] text-[var(--color-ink-2)]">
                  {playing.contextNotes}
                </p>
              )}
              <p className="mt-2 text-[11px] text-[var(--color-ink-2)]">
                {PLACE_BASIS_LABEL[playing.placeBasis]}
              </p>
              <a href={playing.sourceUrl} target="_blank" rel="noopener noreferrer"
                 className="mt-1 inline-block text-[11px] text-[var(--color-accent)]">
                Source page
              </a>
            </footer>
          )}
        </aside>
      )}

      <p className="absolute bottom-4 left-4 z-20 hidden rounded-lg border sm:block
                    border-[var(--color-line)] bg-[var(--color-panel)] px-3 py-2
                    text-xs text-[var(--color-ink-2)] backdrop-blur">
        Drag to spin &middot; click a place to open it
      </p>
    </main>
  );
}
