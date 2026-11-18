# Testing DST gaps and overlaps: nonexistent and ambiguous local times

Twice a year in most DST zones, local wall-clock time either skips forward (a **gap**: some local times never happen) or repeats (an **overlap**: some local times happen twice). Code that turns a local date-time into a UTC instant must decide what to do in both cases. Bugs here show up as jobs that never run, run twice, or land an hour off, often only in one zone.

## The two cases, with real 2026 values
All values below come from `sample/dst_test_vectors_sample.json` (IANA tzdata 2026f).

**Gap (spring forward).** America/New_York, 2026-03-08: the clock jumps from 01:59:59 to 03:00:00, so `02:30` does not exist.
- Read with the offset before the change (-05:00): `2026-03-08T07:30:00Z`
- Read with the offset after it (-04:00): `2026-03-08T06:30:00Z`
- Common default ("compatible"): the first one, so the wall time moves forward to 03:30.

**Overlap (fall back).** America/New_York, 2026-11-01: 01:00-01:59:59 happens twice, so `01:30` is ambiguous.
- Earlier instant (EDT, -04:00): `2026-11-01T05:30:00Z`
- Later instant (EST, -05:00): `2026-11-01T06:30:00Z`
- Common default: the earlier one.

## Zones that break assumptions
| Zone | 2026 change | Why it catches bugs |
|---|---|---|
| America/Havana | 2026-03-08: 00:00 -> 01:00 | Midnight does not exist that day; "start of day = 00:00" is wrong |
| Australia/Lord_Howe | 2026-04-05: 02:00 -> 01:30; 2026-10-04: 02:00 -> 02:30 | DST is 30 minutes, not an hour |
| Pacific/Chatham | +13:45 -> +12:45 on 2026-04-05 | Offsets are not whole or half hours |
| Europe/London | 2026-03-29 01:00 -> 02:00 | Gap at 01:00 local, not 02:00 |

## How common libraries resolve them
- **Python `zoneinfo`**: `datetime(..., tzinfo=ZoneInfo(z), fold=0)` gives the "compatible" result for both gaps and overlaps; `fold=1` gives the later instant of an overlap (and the offset after the change in a gap).
- **JavaScript Temporal**: `disambiguation: "compatible"` (the default) behaves the same way; `"earlier"`, `"later"` and `"reject"` are the alternatives.
- **iCalendar (RFC 5545)**: a nonexistent DTSTART is read with the offset before the gap; an ambiguous one means the first occurrence.
- **Postgres** `timestamp AT TIME ZONE`: check your version's documentation and test it; do not assume.

## Testing with the vectors
Each case in the JSON has the zone, the local wall time, `exists`, `ambiguous`, every UTC instant the wall time can mean, and `compatible_utc`:

```python
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def to_utc(zone, local):          # replace with the function you want to test
    return datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)

for c in json.load(open("sample/dst_test_vectors_sample.json"))["cases"]:
    got = to_utc(c["zone"], c["local"]).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert got == c["compatible_utc"], (c["zone"], c["local"], got)
```

`tests/test_vectors.py` and `tests/check_vectors.mjs` (JavaScript `Intl`, no dependencies) run fuller checks. Results depend on your runtime's tz database version: an old one can disagree with newer rules.

The sample covers 2026 in 5 zones. The full set has 51,404 cases for every zone, 2000-2050, plus the full transitions table with database loaders; see the README.
