"use client";

// "use client" marks this file as a CLIENT component: it ships to the browser and
// runs there. It has to, because a globe is WebGL and WebGL needs a real canvas,
// a GPU and a window. Everything else in this app is a server component that runs
// once at build time and arrives as finished HTML.
//
// This file is the conductor. It owns the STATE (which place is open, what is
// playing, which layers are on) and hands pieces of it to the components that draw:
// Legend, HubPanel, Player, and the globe itself. The rules those components follow
// live in lib/: markers.ts (how a place looks), prayer.ts (the live layer),
// playback.ts (what plays next), search.ts.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import * as THREE from "three";
import type { Family, Genre, PlaceBasis, SoundHub, SoundTrack } from "@/lib/types";
import { FAMILY, GLYPH, PLACE_BASIS_ORDER } from "@/lib/types";
import { buildMarker, type HubView } from "@/lib/markers";
import { formatIn, hubPrayerStatus, prayerLines, sunVector, type PrayerLine } from "@/lib/prayer";
import { makeDayNightMaterial, setSun } from "@/lib/dayNight";
import { pickDriftStop, transition } from "@/lib/playback";
import { buildIndex, type SearchHit } from "@/lib/search";
import Legend, { type SkinName } from "./Legend";
import HubPanel from "./HubPanel";
import Player from "./Player";

// Where this site lives on its host: "" locally, "/sawt" on GitHub Pages. Next
// rewrites its OWN links from basePath, but not strings we build ourselves, like
// texture and audio URLs. See claude/deployment.md: this is the load-bearing detail.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const tex = (name: string) => `${BASE_PATH}/textures/${name}`;

// react-globe.gl reaches for `window` the moment it is imported, and during a build
// there is no window. ssr:false loads it only in the browser.
const Globe = dynamic(() => import("react-globe.gl"), { ssr: false });

// Textures now ship with the site (public/textures) instead of loading from
// unpkg.com, so a network that blocks unpkg no longer shows a black sphere.
const SKINS: Record<SkinName, string> = {
  muted: tex("earth-dark.jpg"),
  daylight: tex("earth-blue-marble.jpg"),
  night: tex("earth-night.jpg"),
};

const PANEL_PX = 384;        // side card width (22rem) plus its margins
const PLAYER_PX = 104;       // player bar height; the sheet and legend make room

// Line widths are in angular degrees of the globe. Maghrib is drawn 1.25° wide on
// purpose: the earth turns 1.25° in five minutes, about the length of one adhan, so
// the band's width IS the stretch of land where the call is sounding right now.
const LINE_STYLE: Record<string, { colour: string; width: number; dash?: [number, number] }> = {
  Fajr: { colour: "#f5c26b", width: 0.35, dash: [0.02, 0.012] },
  Dhuhr: { colour: "rgba(242,245,248,.75)", width: 0.3 },
  Asr: { colour: "#f5c26b", width: 0.35 },
  Maghrib: { colour: "rgba(127,178,240,.85)", width: 1.25 },
  Isha: { colour: "#7fb2f0", width: 0.35, dash: [0.02, 0.012] },
};

/** Parse "#istanbul/fr-12345" into its two parts. */
function readHash(): { hubId: string | null; trackId: string | null } {
  const raw = decodeURIComponent(window.location.hash.replace(/^#/, ""));
  const [hubId, trackId] = raw.split("/");
  return { hubId: hubId || null, trackId: trackId || null };
}

export default function SawtGlobe({ hubs, tracks }: { hubs: SoundHub[]; tracks: SoundTrack[] }) {
  // ---------------- state ----------------
  const [openHubId, setOpenHubId] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<Genre>>(new Set());
  const [skin, setSkin] = useState<SkinName>("muted");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [live, setLive] = useState(false);
  const [drifting, setDrifting] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [pendingMs, setPendingMs] = useState<number | null>(null);
  const [wide, setWide] = useState(false);
  const [ready, setReady] = useState(false);      // the globe has drawn its first frame

  const globeRef = useRef<any>(null);
  const defaultMaterial = useRef<THREE.MeshPhongMaterial | null>(null);
  const dayNight = useRef<ReturnType<typeof makeDayNightMaterial> | null>(null);
  const pendingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const viewShift = useRef(0);

  // ---------------- derived data ----------------
  // useMemo caches a computed value and recomputes only when its inputs change.
  const hubById = useMemo(() => new Map(hubs.map((h) => [h.id, h])), [hubs]);
  const trackById = useMemo(() => new Map(tracks.map((t) => [t.id, t])), [tracks]);
  const visibleTracks = useMemo(() => tracks.filter((t) => !hidden.has(t.genre)), [tracks, hidden]);

  // Group once: Map<hubId, tracks[]>. Everything that needs "the tracks at a place"
  // reads this instead of filtering the whole list again.
  const visibleByHub = useMemo(() => {
    const groups = new Map<string, SoundTrack[]>();
    visibleTracks.forEach((t) => groups.set(t.hubId, [...(groups.get(t.hubId) ?? []), t]));
    return groups;
  }, [visibleTracks]);

  const openHub = openHubId ? hubById.get(openHubId) ?? null : null;
  const playing = playingId ? trackById.get(playingId) ?? null : null;
  const openTracks = openHub ? visibleByHub.get(openHub.id) ?? [] : [];

  // The list the player steps through: the playing track's own place, so prev and
  // next always stay within one soundscape even if another place is open.
  const queue = playing ? visibleByHub.get(playing.hubId) ?? [playing] : [];
  const queuePos = playing ? queue.findIndex((t) => t.id === playing.id) : -1;

  const hubViews: HubView[] = useMemo(() => {
    return hubs.flatMap((h) => {
      const list = visibleByHub.get(h.id) ?? [];
      if (!list.length && !h.isAnchor) return [];      // a filtered-out place disappears
      const fam = new Map<Family, number>();
      const basisMix: Partial<Record<PlaceBasis, number>> = {};
      const glyphs = new Set(list.map((t) => GLYPH[t.genre]));
      list.forEach((t) => {
        fam.set(FAMILY[t.genre], (fam.get(FAMILY[t.genre]) ?? 0) + 1);
        basisMix[t.placeBasis] = (basisMix[t.placeBasis] ?? 0) + 1;
      });
      // The STRONGEST evidence present decides the marker's outline. A place with
      // even one geotagged recording is a place we know sound came from; the list
      // rows then show which of its recordings are less certain.
      const best = PLACE_BASIS_ORDER.find((b) => basisMix[b]) ?? null;
      const status = live && list.length ? hubPrayerStatus(h.lat, h.lng, now) : null;
      return [{
        ...h,
        visibleCount: list.length,
        families: [...fam.entries()].sort((a, b) => b[1] - a[1]),
        glyph: glyphs.size === 1 ? [...glyphs][0] : null,
        basisMix, best,
        selected: h.id === openHubId,
        callingNow: status?.callingNow ?? null,
        nextPrayer: status?.next ? `${status.next.prayer} in ${formatIn(status.next.minutes)}` : null,
      }];
    });
  }, [hubs, visibleByHub, openHubId, live, now]);

  const lines: PrayerLine[] = useMemo(() => (live ? prayerLines(now) : []), [live, now]);

  const genreCounts = useMemo(() => {
    const counts = new Map<Genre, number>();
    tracks.forEach((t) => counts.set(t.genre, (counts.get(t.genre) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [tracks]);

  const index = useMemo(() => buildIndex(hubs, tracks), [hubs, tracks]);

  const liveSummary = useMemo(() => {
    if (!live) return null;
    const calling = hubViews.filter((h) => h.callingNow);
    if (!calling.length) return "No mapped place is mid-adhan this minute.";
    return `Being called now: ${calling.map((h) => `${h.callingNow} in ${h.name}`).join(", ")}.`;
  }, [live, hubViews]);

  // ---------------- camera ----------------
  // Keep the open place centred in the space LEFT of the side card, not behind it.
  // camera.setViewOffset shifts the rendered picture sideways without shrinking the
  // canvas, so the starfield still fills the screen. The HTML markers use the same
  // camera matrices, so they shift with it and stay on their cities.
  const shiftView = useCallback((target: number) => {
    const camera = globeRef.current?.camera?.();
    if (!camera) return;
    const start = viewShift.current;
    const t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 600);
      const eased = 1 - Math.pow(1 - k, 3);                    // ease-out cubic
      const x = start + (target - start) * eased;
      viewShift.current = x;
      const w = window.innerWidth, h = window.innerHeight;
      if (Math.abs(x) < 0.5) camera.clearViewOffset();
      else camera.setViewOffset(w, h, x, 0, w, h);
      camera.updateProjectionMatrix();
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, []);

  useEffect(() => {
    const onResize = () => {
      setWide(window.innerWidth >= 640);
      // setViewOffset remembers the window size it was given, so a resize has to
      // restate it or the picture drifts off-centre.
      const camera = globeRef.current?.camera?.();
      if (camera && Math.abs(viewShift.current) >= 0.5) {
        const w = window.innerWidth, h = window.innerHeight;
        camera.setViewOffset(w, h, viewShift.current, 0, w, h);
        camera.updateProjectionMatrix();
      }
    };
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (ready) shiftView(openHub && wide ? PANEL_PX / 2 : 0);
  }, [openHub, wide, ready, shiftView]);

  // ---------------- actions ----------------
  const clearPending = () => {
    if (pendingTimer.current) clearTimeout(pendingTimer.current);
    pendingTimer.current = null;
    setPendingMs(null);
  };

  const openPlace = useCallback((hub: SoundHub, opts: { fromDrift?: boolean } = {}) => {
    if (!opts.fromDrift) setDrifting(false);       // a manual choice ends Drift
    setOpenHubId(hub.id);
    // An empty anchor has nothing to list, so its essay IS the content: open it.
    setAboutOpen(!(visibleByHub.get(hub.id)?.length) && !!hub.historicalContext);
    globeRef.current?.pointOfView({ lat: hub.lat, lng: hub.lng, altitude: 1.5 }, 900);
  }, [visibleByHub]);

  function play(track: SoundTrack) {
    clearPending();
    setDrifting(false);
    setPlayingId(track.id);
  }

  // Move to `next` after the silence the transition rule asks for.
  function playAfterSilence(next: SoundTrack, from: SoundTrack | null, then?: () => void) {
    clearPending();
    const { silenceMs } = transition(from, next);
    setPendingMs(silenceMs);
    pendingTimer.current = setTimeout(() => {
      setPendingMs(null);
      setPlayingId(next.id);
      then?.();
    }, silenceMs);
  }

  function driftHop() {
    const stop = pickDriftStop(hubs, visibleByHub, playing?.hubId ?? openHubId);
    if (!stop) return;
    playAfterSilence(stop.track, playing, () => openPlace(stop.hub, { fromDrift: true }));
  }

  function onEnded() {
    if (drifting) return driftHop();
    const next = queue[queuePos + 1];
    if (next) playAfterSilence(next, playing);     // autoplay within the same place
  }

  function startDrift() {
    if (drifting) { setDrifting(false); return; }
    setDrifting(true);
    const stop = pickDriftStop(hubs, visibleByHub, playing?.hubId ?? null);
    if (!stop) return;
    clearPending();
    setPlayingId(stop.track.id);          // a click just happened, so audio may start
    openPlace(stop.hub, { fromDrift: true });
  }

  function onPick(hit: SearchHit) {
    openPlace(hit.hub);
    if (hit.track) play(hit.track);
  }

  function toggleGenre(genre: Genre) {
    setHidden((current) => {
      // React state must never be mutated in place: make a new Set, or React cannot
      // tell anything changed and will not re-render.
      const next = new Set(current);
      if (next.has(genre)) next.delete(genre); else next.add(genre);
      return next;
    });
  }

  // ---------------- deep links: #hub/track ----------------
  // The URL is the one piece of state that can leave this browser. Reading it on
  // load and writing it on every change means any view can be shared by copying
  // the address bar.
  const applyHash = useCallback(() => {
    const { hubId, trackId } = readHash();
    const hub = hubId ? hubById.get(hubId) : undefined;
    if (!hub) return;
    openPlace(hub);
    if (trackId && trackById.get(trackId)?.hubId === hub.id) setPlayingId(trackId);
  }, [hubById, trackById, openPlace]);

  // Read the link once on arrival. This only sets STATE, so it does not need the
  // globe to exist yet; the camera catches up in the effect below once it does.
  // (The empty dependency list [] means "run once, after the first render".)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { applyHash(); }, []);

  useEffect(() => {
    if (!ready || !openHub) return;
    globeRef.current?.pointOfView({ lat: openHub.lat, lng: openHub.lng, altitude: 1.5 }, 900);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  useEffect(() => {
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, [applyHash]);

  useEffect(() => {
    // replaceState, not location.hash = ...: changing the hash directly would add a
    // history entry per click (Back would step through every track) and fire our
    // own hashchange listener.
    // The open place wins; the track joins it only if it belongs there. So the
    // address always describes what is on screen, and a link opens the same view.
    const hubPart = openHubId ?? playing?.hubId ?? null;
    const trackPart = playing && playing.hubId === hubPart ? playing.id : null;
    const hash = hubPart ? `#${hubPart}${trackPart ? "/" + trackPart : ""}` : "";
    const url = window.location.pathname + window.location.search + hash;
    if (url !== window.location.pathname + window.location.search + window.location.hash) {
      window.history.replaceState(null, "", url);
    }
  }, [openHubId, playing]);

  // ---------------- live layer ----------------
  useEffect(() => {
    if (!live) return;
    setNow(new Date());
    // The lines move about 0.125° every 30 seconds: fast enough to see, slow enough
    // that redrawing more often would only burn battery.
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, [live]);

  // The globe's surface material. globeMaterial is a PROP of react-globe.gl, not a
  // method on its ref, so the choice is made in render: the sunlit shader while the
  // live layer is on, otherwise a plain Phong material (what globe.gl uses by
  // default) which receives the chosen basemap texture. Both are created once and
  // kept in refs, because building a material every render would leak GPU memory.
  const surface = useMemo(() => {
    if (typeof window === "undefined") return undefined;
    if (!defaultMaterial.current) defaultMaterial.current = new THREE.MeshPhongMaterial({ color: 0xffffff });
    if (!live) return defaultMaterial.current;
    dayNight.current ??= makeDayNightMaterial(tex("earth-blue-marble.jpg"), tex("earth-night.jpg"));
    return dayNight.current;
  }, [live]);

  useEffect(() => {
    if (live && dayNight.current) setSun(dayNight.current, sunVector(now));
  }, [live, now]);

  // Stop any pending transition if the component goes away.
  useEffect(() => () => clearPending(), []);

  // ---------------- render ----------------
  return (
    <main className="relative h-dvh w-full overflow-hidden"
          style={{ ["--player-h" as string]: playing ? `${PLAYER_PX}px` : "0px" }}>
      <div className="absolute inset-0 z-0">
        <Globe
          ref={globeRef}
          onGlobeReady={() => {
            setReady(true);
          }}
          globeMaterial={surface}
          globeImageUrl={SKINS[skin]}
          bumpImageUrl={tex("earth-topology.png")}
          backgroundImageUrl={tex("night-sky.png")}
          atmosphereColor="#79a9e0"
          atmosphereAltitude={0.15}
          htmlElementsData={hubViews}
          htmlLat={(d: any) => d.lat}
          htmlLng={(d: any) => d.lng}
          htmlAltitude={0.01}
          htmlElement={(d: any) => buildMarker(d as HubView, (hub) => openPlace(hub))}
          htmlElementVisibilityModifier={(el: HTMLElement, isVisible: boolean) => {
            // Hide markers on the far side of the sphere.
            el.style.opacity = isVisible ? "1" : "0";
            el.style.pointerEvents = isVisible ? "auto" : "none";
          }}
          pathsData={lines}
          pathPoints={(d: any) => d.points}
          pathPointLat={(p: any) => p[0]}
          pathPointLng={(p: any) => p[1]}
          pathPointAlt={0.004}
          pathColor={(d: any) => LINE_STYLE[d.prayer].colour}
          pathStroke={(d: any) => LINE_STYLE[d.prayer].width}
          pathDashLength={(d: any) => LINE_STYLE[d.prayer].dash?.[0] ?? 1}
          pathDashGap={(d: any) => LINE_STYLE[d.prayer].dash?.[1] ?? 0}
          pathLabel={(d: any) => `${d.prayer} is being called along this line`}
          pathTransitionDuration={0}
        />
      </div>

      {/* A scrim on phones: darkens the globe behind the sheet and closes it on tap. */}
      {openHub && (
        <button aria-label="Close panel" onClick={() => setOpenHubId(null)}
                className="fixed inset-0 z-30 bg-black/55 sm:hidden" />
      )}

      <Legend
        trackCount={visibleTracks.length}
        placeCount={hubViews.filter((h) => h.visibleCount > 0).length}
        undatedCount={visibleTracks.filter((t) => t.dateBasis === "unknown").length}
        genreCounts={genreCounts}
        hidden={hidden}
        onToggleGenre={toggleGenre}
        skin={skin}
        onSkin={setSkin}
        live={live}
        onLive={() => setLive((v) => !v)}
        liveSummary={liveSummary}
        drifting={drifting}
        onDrift={startDrift}
        index={index}
        onPick={onPick}
      />

      {openHub && (
        <HubPanel
          hub={openHub}
          tracks={openTracks}
          playingId={playingId}
          aboutOpen={aboutOpen}
          prayerNote={(() => {
            const v = hubViews.find((h) => h.id === openHub.id);
            if (!v) return null;
            return v.callingNow ? `${v.callingNow} is being called here now`
                 : v.nextPrayer ? `Next here: ${v.nextPrayer}` : null;
          })()}
          onToggleAbout={() => setAboutOpen((o) => !o)}
          onPlay={play}
          onClose={() => setOpenHubId(null)}
        />
      )}

      {playing ? (
        <Player
          track={playing}
          hub={hubById.get(playing.hubId)}
          hasPrev={queuePos > 0}
          hasNext={drifting || queuePos < queue.length - 1}
          drifting={drifting}
          pendingMs={pendingMs}
          onPrev={() => { clearPending(); setPlayingId(queue[queuePos - 1].id); }}
          onNext={() => {
            if (drifting) return driftHop();
            clearPending();
            setPlayingId(queue[queuePos + 1].id);
          }}
          onEnded={onEnded}
          onStop={() => { clearPending(); setDrifting(false); setPlayingId(null); }}
          onStopDrift={() => setDrifting(false)}
          onShowPlace={() => { const h = hubById.get(playing.hubId); if (h) openPlace(h, { fromDrift: drifting }); }}
        />
      ) : (
        <p className="absolute bottom-4 left-4 z-20 hidden rounded-lg border border-[var(--color-line)]
                      bg-[var(--color-panel)] px-3 py-2 text-xs text-[var(--color-ink-2)] sm:block">
          Drag to spin &middot; hover a place to see what is there &middot; click to open it
        </p>
      )}
    </main>
  );
}
