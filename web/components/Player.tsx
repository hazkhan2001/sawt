"use client";

// The player bar. It lives OUTSIDE the hub panel now, so closing a place, opening
// another, or drifting across the globe never cuts the sound off, and it always
// says what is playing and where, instead of relying on a highlighted row that
// may not even be on screen.

import { useEffect, useRef, useState } from "react";
import type { SoundHub, SoundTrack } from "@/lib/types";
import { GENRE_LABEL } from "@/lib/types";
import { formatDuration } from "@/lib/data";
import { DRIFT_STAY_SECONDS, driftMayCut } from "@/lib/playback";
import { GenreGlyph, Icon } from "./Icons";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

interface Props {
  track: SoundTrack;
  hub: SoundHub | undefined;
  hasPrev: boolean;
  hasNext: boolean;
  drifting: boolean;
  pendingMs: number | null;            // a silence before the next track, if any
  onPrev: () => void;
  onNext: () => void;
  onEnded: () => void;
  onStop: () => void;
  onStopDrift: () => void;
  onShowPlace: () => void;
}

export default function Player(props: Props) {
  const { track, hub, drifting } = props;
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(track.durationSeconds ?? 0);
  const [copied, setCopied] = useState(false);
  const [blocked, setBlocked] = useState(false);
  // A ref, not state: "have we already moved on from this track?" must be readable
  // immediately inside an event handler, and must not cause a re-render.
  const movedOn = useRef(false);

  // A new track: reset the clock and try to start. Browsers refuse to autoplay
  // sound until the visitor has interacted with the page, which is what happens
  // when someone opens a shared link cold. play() returns a Promise that REJECTS in
  // that case, so we catch it and show a play button instead of failing silently.
  useEffect(() => {
    setTime(0);
    setDuration(track.durationSeconds ?? 0);
    setBlocked(false);
    movedOn.current = false;
    const audio = audioRef.current;
    if (!audio) return;
    audio.play().catch(() => setBlocked(true));
  }, [track.id, track.durationSeconds]);

  function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) audio.play().then(() => setBlocked(false)).catch(() => setBlocked(true));
    else audio.pause();
  }

  function onTimeUpdate() {
    const audio = audioRef.current!;
    setTime(audio.currentTime);
    // Drift moves on after a while, except from an adhan, which plays to its end.
    if (drifting && driftMayCut(track) && audio.currentTime >= DRIFT_STAY_SECONDS && !movedOn.current) {
      movedOn.current = true;
      audio.pause();
      props.onEnded();
    }
  }

  async function copyLink() {
    // The same URL the address bar already shows, because SawtGlobe keeps the hash
    // in step with what is playing. Copying it is just a convenience.
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch { /* clipboard refused (insecure context): the address bar still works */ }
  }

  const credit = [track.license, track.attribution ? "by " + track.attribution : null]
    .filter(Boolean).join(" · ");
  const driftLeft = drifting && driftMayCut(track)
    ? Math.max(0, Math.ceil(DRIFT_STAY_SECONDS - time)) : null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-[var(--color-line)]
                    bg-[var(--color-panel)] px-4 pb-3 pt-2.5 shadow-2xl
                    sm:inset-x-auto sm:bottom-4 sm:left-4 sm:w-[26rem] sm:rounded-xl sm:border"
         style={{ height: "var(--player-h)" }}>
      <audio
        ref={audioRef}
        key={track.id}
        src={`${BASE_PATH}/${track.audioUrl}`}
        preload="auto"
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => { setIsPlaying(false); props.onEnded(); }}
        onTimeUpdate={onTimeUpdate}
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration;
          if (isFinite(d)) setDuration(d);
        }}
      />

      <div className="flex items-center gap-3">
        <GenreGlyph genre={track.genre} size={12} />
        <div className="min-w-0 flex-1">
          {/* dir="auto": the browser picks left-to-right or right-to-left from the
              first strong character, so an Arabic title reads from the right. */}
          <p dir="auto" className="truncate text-[13px] font-medium leading-snug">
            {track.displayTitle}
          </p>
          <button onClick={props.onShowPlace}
                  className="block max-w-full truncate text-left text-[11px] text-[var(--color-ink-2)] hover:text-[var(--color-accent)]">
            {hub ? `${hub.name}${hub.country ? ", " + hub.country : ""}` : ""} · {GENRE_LABEL[track.genre]}
          </button>
        </div>

        <div className="flex shrink-0 items-center gap-0.5 text-[var(--color-ink)]">
          <button onClick={props.onPrev} disabled={!props.hasPrev} aria-label="Previous recording"
                  className="rounded-md p-1.5 hover:bg-white/5 disabled:opacity-25">
            <Icon name="prev" />
          </button>
          <button onClick={toggle} aria-label={isPlaying ? "Pause" : "Play"}
                  className={"rounded-full p-2 hover:bg-white/10 " +
                             (blocked ? "bg-[var(--color-accent)] text-[#05070a]" : "bg-white/5")}>
            <Icon name={isPlaying ? "pause" : "play"} />
          </button>
          <button onClick={props.onNext} disabled={!props.hasNext} aria-label="Next recording"
                  className="rounded-md p-1.5 hover:bg-white/5 disabled:opacity-25">
            <Icon name="next" />
          </button>
          <button onClick={copyLink} aria-label="Copy link to this recording"
                  className="rounded-md p-1.5 text-[var(--color-ink-2)] hover:bg-white/5 hover:text-white">
            <Icon name="link" size={16} />
          </button>
          <button onClick={props.onStop} aria-label="Stop and close the player"
                  className="rounded-md p-1.5 text-[var(--color-ink-2)] hover:bg-white/5 hover:text-white">
            <Icon name="close" size={16} />
          </button>
        </div>
      </div>

      <div className="mt-1.5 flex items-center gap-2 text-[10.5px] tabular-nums text-[var(--color-ink-2)]">
        <span className="w-8">{formatDuration(time) || "0:00"}</span>
        {/* A range input IS a seek bar: keyboard-operable and accessible for free. */}
        <input type="range" min={0} max={duration || 1} step={0.5} value={Math.min(time, duration || 1)}
               aria-label="Seek"
               onChange={(e) => {
                 const audio = audioRef.current;
                 if (audio) audio.currentTime = Number(e.target.value);
               }}
               className="sawt-range flex-1" />
        <span className="w-8 text-right">{formatDuration(duration)}</span>
      </div>

      {/* The credit line is ALWAYS visible while a track plays. For CC BY and
          CC BY-SA it is a condition of the licence, not a courtesy (rule 14), so
          no status message is ever allowed to replace it. Status sits beside it. */}
      <div className="mt-1 flex items-baseline gap-3 text-[10.5px] text-[var(--color-ink-2)]">
        <p className="min-w-0 flex-1 truncate" title={credit}>{credit}</p>
        <p className="shrink-0 text-[var(--color-accent)]">
          {copied ? "Link copied" :
           props.pendingMs ? "Pause…" :
           blocked ? "Press play" :
           drifting ? (
             <>
               {driftLeft !== null ? `Drift · next in ${formatDuration(driftLeft)}` : "Drift · plays to the end"}
               <button onClick={props.onStopDrift} aria-label="Stop drifting"
                       className="ml-1.5 rounded border border-[var(--color-line)] px-1 text-[var(--color-ink-2)] hover:text-white">
                 stop
               </button>
             </>
           ) : null}
        </p>
      </div>
    </div>
  );
}
