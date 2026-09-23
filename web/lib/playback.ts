// Rules about what plays next, kept apart from the component so they can be read
// (and one day tested) on their own.

import type { SoundTrack, SoundHub } from "./types";

// Spec rule 8: the adhan is never faded into or out of other audio, and never
// played underneath anything. With a plain <audio> element there IS no crossfade,
// so today this only decides how long the silence is. The point of writing it as a
// function now is Phase 3: when Howler arrives with crossfades, every transition
// already goes through this one gate, and nobody has to remember the rule.
export function transition(from: SoundTrack | null, to: SoundTrack) {
  const sacred = from?.genre === "adhan" || to.genre === "adhan";
  return {
    crossfade: false as const,            // Phase 3 may allow true when !sacred
    silenceMs: sacred ? 2500 : 900,       // a real pause either side of a call
  };
}

// Drift mode: how long to stay before moving on. Field recordings can run twenty
// minutes, and Drift is for wandering. But an adhan is never cut off mid-call; it
// plays to its end, however long.
export const DRIFT_STAY_SECONDS = 120;
export const driftMayCut = (track: SoundTrack) => track.genre !== "adhan";

/**
 * Choose the next Drift stop. Every PLACE is equally likely, not every recording:
 * picking by recording would send you to Istanbul (14 tracks) fourteen times as
 * often as to Almaty (one). The 41 single-recording hubs are what Drift is for.
 */
export function pickDriftStop(
  hubs: SoundHub[], tracksByHub: Map<string, SoundTrack[]>, currentHubId: string | null,
): { hub: SoundHub; track: SoundTrack } | null {
  const candidates = hubs.filter((h) => h.id !== currentHubId && (tracksByHub.get(h.id)?.length ?? 0) > 0);
  if (!candidates.length) return null;
  const hub = candidates[Math.floor(Math.random() * candidates.length)];
  const list = tracksByHub.get(hub.id)!;
  return { hub, track: list[Math.floor(Math.random() * list.length)] };
}
