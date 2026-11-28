# Convert UTC to local time in SQL with a time zone transitions table

Most databases can convert time zones, but not all the same way: MySQL needs its time zone tables loaded, SQL Server's `AT TIME ZONE` uses Windows zone names, and warehouses and SQLite often have no zone support at all. A plain table of offset changes works the same in every engine, joins like any other table, and shows exactly which rules you are using.

## The table
One row per change, per zone (from the IANA tz database):

| zone | utc | local_before | local_after | offset_before_s | offset_after_s | abbr_after | kind |
|---|---|---|---|---|---|---|---|
| America/Chicago | 2026-03-08T08:00:00Z | 2026-03-08T02:00:00 | 2026-03-08T03:00:00 | -21600 | -18000 | CDT | gap |
| America/Chicago | 2026-11-01T07:00:00Z | 2026-11-01T02:00:00 | 2026-11-01T01:00:00 | -18000 | -21600 | CST | overlap |

Rule: the offset in effect at instant `t` is `offset_after_s` of the zone's latest row with `utc <= t`. If there is no such row (zones such as Asia/Kolkata have not changed since 1970), use the zone's offset at the start of the table.

## PostgreSQL
Tested on PostgreSQL 16 with the full set loaded (`sql/postgres.sql`):

```sql
WITH ev(id, zone, t) AS (VALUES
  (1, 'America/Chicago', '2026-03-08 07:59:59Z'::timestamptz),
  (2, 'America/Chicago', '2026-03-08 08:00:00Z'::timestamptz),
  (3, 'Asia/Kolkata',    '2026-03-08 08:00:00Z'::timestamptz))
SELECT ev.id, ev.zone,
       (ev.t AT TIME ZONE 'UTC') + make_interval(secs => COALESCE(o.off, z.offset_at_start_s)) AS local_time,
       COALESCE(o.abbr, z.abbr_at_start) AS abbr
FROM ev
JOIN tz_zone z ON z.zone = ev.zone
LEFT JOIN LATERAL (
  SELECT tr.offset_after_s AS off, tr.abbr_after AS abbr
  FROM tz_transition tr
  WHERE tr.zone = ev.zone AND tr.utc <= ev.t
  ORDER BY tr.utc DESC LIMIT 1) o ON true
ORDER BY ev.id;
```

Result:

```
1 | America/Chicago | 2026-03-08 01:59:59 | CST
2 | America/Chicago | 2026-03-08 03:00:00 | CDT
3 | Asia/Kolkata    | 2026-03-08 13:30:00 | IST
```

With an index on `(zone, utc)` (the full set's Postgres loader creates `tz_transition_zone_utc`; add it yourself if you load the CSV another way), the lateral lookup is one index probe per row.

## MySQL / MariaDB
Store instants as Unix seconds and look up the latest change (tested on MariaDB 10.11):

```sql
SELECT e.id,
       FROM_UNIXTIME(e.unix_ts + COALESCE(
         (SELECT tr.offset_after_s FROM tz_transition tr
           WHERE tr.zone = e.zone AND tr.unix <= e.unix_ts ORDER BY tr.unix DESC LIMIT 1),
         (SELECT z.offset_at_start_s FROM tz_zone z WHERE z.zone = e.zone))) AS local_time
FROM events e;
```

`FROM_UNIXTIME` formats in the session time zone, so run `SET time_zone = '+00:00';` first.

## Useful queries on the table itself
- Next year's DST changes for your zones: `WHERE zone IN (...) AND utc >= '2027-01-01' AND utc < '2028-01-01'`.
- Zones whose changes are not one hour (after 2026: Antarctica/Troll, Australia/Lord_Howe): `WHERE abs(delta_s) NOT IN (0, 3600)`.
- Local times that do not exist (gaps) or repeat (overlaps): rows with `kind = 'gap'` cover `[local_before, local_after)`; rows with `kind = 'overlap'` repeat `[local_after, local_before)`.

## Keeping it current
Governments change rules several times a year, and the IANA database follows. Rebuild the table when a new tzdata release affects your zones.

This repo has a free sample (16 zones, 2026-2030). The full set covers all 344 canonical zones and 253 aliases, 1970-2050, with tested PostgreSQL and MySQL/MariaDB loaders; see the [README](../README.md). The [full set](https://buy.polar.sh/polar_cl_IbPBiFVd3r1YmjO4XDcsCvCTG1DqmQIOPmld92JZG2z?utm_source=github&utm_medium=readme&utm_campaign=D&utm_content=tz-transitions) is $15, one-time (Polar is the merchant of record and handles sales tax). It is also in the [calendar data bundle](https://buy.polar.sh/polar_cl_HiUeTqJE1gUqHdb3OlOWb6Jml7pdq8E71O2pA4Y9iQ3?utm_source=github&utm_medium=readme&utm_campaign=BUNDLE&utm_content=tz-transitions) (US business-day calendar, date dimension and time zone packs) for $35 instead of $49.
