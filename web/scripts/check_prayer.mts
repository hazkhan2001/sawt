// Cross-check: our solar-geometry lines against adhan-js's own times.
// Run:  node scripts/check_prayer.mts      (Node 22.18+ runs TypeScript directly)
//
// The lines and the hub times come from two independent calculations. If a point
// picked off our Maghrib line does not have an adhan-js sunset within a couple of
// minutes of "now", one of them is wrong, and the map would be quietly lying.
import { Coordinates, CalculationMethod, PrayerTimes } from "adhan";
import { prayerLines } from "../lib/prayer.ts";

const KEY = { Fajr: "fajr", Dhuhr: "dhuhr", Asr: "asr", Maghrib: "maghrib", Isha: "isha" } as const;
let worst = 0, checked = 0;
for (const iso of ["2026-03-20T12:00:00Z", "2026-06-21T03:30:00Z", "2026-09-23T17:45:00Z", "2026-12-21T21:10:00Z"]) {
  const now = new Date(iso);
  for (const line of prayerLines(now)) {
    for (const [lat, lng] of line.points.filter((_, i) => i % 7 === 0)) {
      if (Math.abs(lat) > 55) continue;          // adhan-js applies high-latitude rules there
      let best = Infinity;
      for (const d of [-1, 0, 1]) {
        const pt = new PrayerTimes(new Coordinates(lat, lng), new Date(now.getTime() + d * 864e5),
                                   CalculationMethod.MuslimWorldLeague());
        const t = pt[KEY[line.prayer]];
        if (t) best = Math.min(best, Math.abs(t.getTime() - now.getTime()) / 60000);
      }
      worst = Math.max(worst, best); checked++;
      if (best > 3) console.log("OFF", iso, line.prayer, lat, lng.toFixed(2), best.toFixed(1), "min");
    }
  }
}
console.log(`${checked} points checked, worst disagreement ${worst.toFixed(1)} min`);
process.exit(worst > 3 ? 1 : 0);
