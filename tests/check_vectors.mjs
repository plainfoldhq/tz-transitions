// Check dst_test_vectors.json with JavaScript Intl (no dependencies): every UTC instant
// in a case must format to the case's wall time (or, for gaps, must NOT).
// Run: node tests/check_vectors.mjs   (results depend on your runtime's ICU tz version)
import { readFileSync } from "node:fs";
const V = JSON.parse(readFileSync(new URL("../sample/dst_test_vectors_sample.json", import.meta.url)));
const fmts = new Map();
function wall(zone, iso) {
  if (!fmts.has(zone)) fmts.set(zone, new Intl.DateTimeFormat("en-CA", { timeZone: zone, hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  const p = Object.fromEntries(fmts.get(zone).formatToParts(new Date(iso)).map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}
let bad = 0, n = 0;
for (const c of V.cases) {
  const keys = c.ambiguous ? ["utc_earlier", "utc_later"] : c.exists ? ["utc"] : ["utc_if_offset_before", "utc_if_offset_after"];
  for (const k of keys) {
    n++;
    const same = wall(c.zone, c[k]) === c.local;
    if (same !== c.exists) { if (bad++ < 5) console.log("mismatch", c.zone, c.local, k, wall(c.zone, c[k])); }
  }
}
console.log(`${n} checks, ${bad} mismatches (ICU tz ${process.versions.tz ?? "?"}, vectors tzdata ${V.tzdata_version ?? "?"})`);
process.exit(bad ? 1 : 0);
