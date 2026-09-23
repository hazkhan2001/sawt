// The adhan live layer: where on earth each prayer is being called RIGHT NOW.
//
// Two tools, each used where it is strongest:
//
//   1. Our own solar geometry (below) draws the LINES. A prayer time is defined by
//      the sun's altitude: Maghrib at sunset, Fajr and Isha when the sun is a set
//      number of degrees below the horizon, Asr by shadow length, Dhuhr at the
//      meridian. So "where is Maghrib now?" means "where is the sun at -0.833°
//      right now?", and that has a closed-form answer for each latitude. One
//      formula per latitude, about 130 latitudes, five prayers: instant.
//
//   2. adhan-js computes the TIMES for individual hubs, which is what it is built
//      for, with all the edge cases (high latitudes, rounding, madhab) handled.
//      We use it for "Maghrib is being called here now" and "Isha in 40 min".
//
// A test in scripts/check_prayer.mts checks the two against each other: a point
// taken from our Maghrib line should have an adhan-js sunset within a minute of now.

import { Coordinates, CalculationMethod, PrayerTimes, Madhab } from "adhan";

const RAD = Math.PI / 180;
const DEG = 180 / Math.PI;

/** Normalise any longitude into -180..180. */
const wrapLng = (lng: number) => ((((lng + 180) % 360) + 360) % 360) - 180;

/**
 * Where the sun is overhead at a given instant: its declination (the latitude it
 * is over) and the subsolar longitude. The standard low-precision almanac
 * formulas, good to about 0.01°, which is far below what a globe can show.
 */
export function sunPosition(date: Date) {
  const n = date.getTime() / 86400000 + 2440587.5 - 2451545.0;  // days since J2000
  const L = (280.46 + 0.9856474 * n) % 360;                      // mean longitude
  const g = ((357.528 + 0.9856003 * n) % 360) * RAD;             // mean anomaly
  const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * RAD;
  const eps = (23.439 - 0.0000004 * n) * RAD;                    // earth's tilt
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda)) * DEG;
  const dec = Math.asin(Math.sin(eps) * Math.sin(lambda)) * DEG;
  const gmst = (280.46061837 + 360.98564736629 * n) % 360;      // sidereal time
  return { lat: dec, lng: wrapLng(ra - gmst) };
}

export type PrayerName = "Fajr" | "Dhuhr" | "Asr" | "Maghrib" | "Isha";

// Muslim World League angles, the most widely used default. Asr uses a shadow
// factor of 1 (Shafi'i, Maliki, Hanbali); the Hanafi Asr uses 2 and comes later.
// Changing ASR_SHADOW to 2 redraws the whole line for the Hanafi reckoning.
const FAJR_ANGLE = -18;
const ISHA_ANGLE = -17;
const SUNSET_ANGLE = -0.833;   // refraction plus the sun's radius
export const ASR_SHADOW: 1 | 2 = 1;

export interface PrayerLine {
  prayer: PrayerName;
  points: [number, number][];   // [lat, lng] pairs
}

/**
 * The line on earth where the sun currently stands at `altitude(lat)` degrees,
 * on the morning or afternoon side.
 *
 * The one formula doing the work is the altitude equation from spherical
 * astronomy, solved for the hour angle H:
 *     sin(alt) = sin(lat)·sin(dec) + cos(lat)·cos(dec)·cos(H)
 *  => cos(H)   = (sin(alt) − sin(lat)·sin(dec)) / (cos(lat)·cos(dec))
 * H is how far (in degrees of longitude) a place is from the sun's meridian.
 * If |cos H| > 1 there is no solution: at that latitude the sun never reaches that
 * altitude today (polar summer for Isha, for example), so the line simply stops.
 */
function locus(sun: { lat: number; lng: number }, side: "am" | "pm",
               altitude: (lat: number) => number): [number, number][][] {
  const segments: [number, number][][] = [];
  let current: [number, number][] = [];
  for (let lat = -66; lat <= 66; lat += 1) {
    const phi = lat * RAD, dec = sun.lat * RAD, alt = altitude(lat) * RAD;
    const cosH = (Math.sin(alt) - Math.sin(phi) * Math.sin(dec)) / (Math.cos(phi) * Math.cos(dec));
    if (Math.abs(cosH) > 1) {                 // no solution here: break the line
      if (current.length > 1) segments.push(current);
      current = [];
      continue;
    }
    const H = Math.acos(cosH) * DEG;
    // Afternoon places are EAST of the sun's meridian (the sun has passed them),
    // morning places are west of it.
    const lng = wrapLng(side === "pm" ? sun.lng + H : sun.lng - H);
    // Split where the line crosses the 180° meridian, or it would be drawn the
    // long way round the world.
    const prev = current[current.length - 1];
    if (prev && Math.abs(prev[1] - lng) > 180) {
      segments.push(current);
      current = [];
    }
    current.push([lat, lng]);
  }
  if (current.length > 1) segments.push(current);
  return segments;
}

export function prayerLines(date: Date): PrayerLine[] {
  const sun = sunPosition(date);
  const lines: PrayerLine[] = [];
  const add = (prayer: PrayerName, segs: [number, number][][]) =>
    segs.forEach((points) => lines.push({ prayer, points }));

  add("Fajr", locus(sun, "am", () => FAJR_ANGLE));
  // Dhuhr: the sun's own meridian, from pole to pole, split at nothing.
  add("Dhuhr", [Array.from({ length: 133 }, (_, i) => [i - 66, sun.lng] as [number, number])]);
  // Asr: the altitude depends on latitude, because it is defined by shadow length:
  // shadow = ASR_SHADOW × object + the object's own shadow at noon.
  add("Asr", locus(sun, "pm", (lat) =>
    Math.atan(1 / (ASR_SHADOW + Math.tan(Math.abs(lat - sun.lat) * RAD))) * DEG));
  add("Maghrib", locus(sun, "pm", () => SUNSET_ANGLE));
  add("Isha", locus(sun, "pm", () => ISHA_ANGLE));
  return lines;
}

/** The sun's direction as a unit vector in globe.gl's 3D coordinates (for the shader). */
export function sunVector(date: Date): [number, number, number] {
  const { lat, lng } = sunPosition(date);
  // three-globe's own polar-to-cartesian convention, copied exactly, so the lit
  // hemisphere lines up with the texture.
  const phi = (90 - lat) * RAD;
  const theta = (90 - lng) * RAD;
  return [Math.sin(phi) * Math.cos(theta), Math.cos(phi), Math.sin(phi) * Math.sin(theta)];
}

// ---------------------------------------------------------------------------
// Per-hub times, from adhan-js.
// ---------------------------------------------------------------------------

const PRAYERS: [PrayerName, "fajr" | "dhuhr" | "asr" | "maghrib" | "isha"][] = [
  ["Fajr", "fajr"], ["Dhuhr", "dhuhr"], ["Asr", "asr"], ["Maghrib", "maghrib"], ["Isha", "isha"],
];

// How long after the prayer time we still call it "being called now". An adhan
// itself lasts three to five minutes; a little slack covers late muezzins.
const CALLING_WINDOW_MIN = 8;

export interface HubPrayerStatus {
  callingNow: PrayerName | null;
  next: { prayer: PrayerName; minutes: number } | null;
}

export function hubPrayerStatus(lat: number, lng: number, now: Date): HubPrayerStatus {
  const params = CalculationMethod.MuslimWorldLeague();
  params.madhab = ASR_SHADOW === 2 ? Madhab.Hanafi : Madhab.Shafi;
  const coords = new Coordinates(lat, lng);

  // adhan-js computes for a calendar DATE. "Today" in the viewer's timezone may be
  // yesterday or tomorrow in Kashgar, so compute three days and take whatever is
  // nearest to now. Simpler and safer than working out each hub's timezone.
  const times: { prayer: PrayerName; at: number }[] = [];
  for (const dayOffset of [-1, 0, 1]) {
    const day = new Date(now.getTime() + dayOffset * 86400000);
    const pt = new PrayerTimes(coords, day, params);
    for (const [name, key] of PRAYERS) {
      const at = pt[key]?.getTime();
      if (at && !isNaN(at)) times.push({ prayer: name, at });
    }
  }
  const t = now.getTime();
  const past = times.filter((x) => x.at <= t).sort((a, b) => b.at - a.at)[0];
  const future = times.filter((x) => x.at > t).sort((a, b) => a.at - b.at)[0];
  return {
    callingNow: past && t - past.at < CALLING_WINDOW_MIN * 60000 ? past.prayer : null,
    next: future ? { prayer: future.prayer, minutes: Math.round((future.at - t) / 60000) } : null,
  };
}

export function formatIn(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}
