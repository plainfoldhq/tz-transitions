"""DST test vectors: nonexistent (spring-forward gap) and ambiguous (fall-back overlap)
local times, with the UTC instant(s) each one can mean. Standard library only (Python 3.10+).

    import dst_test_vectors as dtv
    for case in dtv.cases(kind="gap"):
        ...
    dtv.check(my_to_utc)            # [] when your function agrees with every case
    dtv.is_ambiguous("2026-11-01T01:30:00", "America/New_York")   # True

The bundled sample covers 2026 in 5 zones (New York, London, Havana, Lord Howe, Chatham),
generated from IANA tzdata 2026f. `load(path)` reads any file in the same format, such as
the full set (2000-2050, every zone): https://github.com/plainfoldhq/tz-transitions
"""
import json
import os
from datetime import datetime, timezone

__version__ = "0.1.0"
__all__ = ["Case", "cases", "load", "check", "params", "to_utc", "is_nonexistent", "is_ambiguous",
           "TZDATA_VERSION"]

_UTC = timezone.utc
_SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sample.json")
KINDS = ("gap", "overlap", "normal")


def _z(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


class Case:
    """One test case. `kind` is "gap" (the local time does not exist), "overlap" (it happens
    twice) or "normal" (exactly once; boundary seconds next to a change).

    `utc` is the single instant for a normal case. For an overlap, `earlier`/`later` are the two
    instants (offset before / after the change). For a gap, `earlier`/`later` are the instants you
    get by applying the offset before / after the change (`earlier` here is the offset-after one,
    so earlier <= later always holds). `compatible` is the usual default resolution: the earlier
    instant in an overlap, the offset before the change in a gap (Python fold=0, RFC 5545,
    Temporal "compatible").
    """
    __slots__ = ("zone", "local", "kind", "utc", "earlier", "later", "compatible", "transition_utc",
                 "tags", "note", "raw")

    def __init__(self, d):
        self.raw = d
        self.zone = d["zone"]
        self.local = datetime.fromisoformat(d["local"])
        self.tags = tuple(d.get("tags", ()))
        self.note = d.get("note", "")
        self.transition_utc = _z(d.get("transition_utc"))
        self.compatible = _z(d["compatible_utc"])
        if d.get("ambiguous"):
            self.kind = "overlap"
            self.earlier, self.later = _z(d["utc_earlier"]), _z(d["utc_later"])
            self.utc = None
        elif not d.get("exists", True):
            self.kind = "gap"
            a, b = _z(d["utc_if_offset_before"]), _z(d["utc_if_offset_after"])
            self.earlier, self.later = min(a, b), max(a, b)
            self.utc = None
        else:
            self.kind = "normal"
            self.utc = _z(d["utc"])
            self.earlier = self.later = self.utc

    @property
    def id(self):
        """Short readable id, e.g. 'America/New_York 2026-11-01T01:00:00 overlap'."""
        return f"{self.zone} {self.local.isoformat()} {self.kind}"

    def __repr__(self):
        return f"Case({self.id!r})"


_cache = {}


def load(path=None):
    """Return (metadata, [Case, ...]) from a vectors JSON file (default: the bundled sample)."""
    path = path or _SAMPLE
    if path not in _cache:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        meta = {k: v for k, v in data.items() if k != "cases"}
        _cache[path] = (meta, [Case(c) for c in data["cases"]])
    return _cache[path]


TZDATA_VERSION = load()[0].get("tzdata_version")


def cases(zone=None, kind=None, tag=None, year=None, path=None):
    """Filter cases. zone: IANA name or list of names; kind: "gap", "overlap", "normal";
    tag: e.g. "midnight", "odd_offset", "delta_30min"; year: local year."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    zones = None if zone is None else {zone} if isinstance(zone, str) else set(zone)
    out = []
    for c in load(path)[1]:
        if zones is not None and c.zone not in zones:
            continue
        if kind and c.kind != kind:
            continue
        if tag and tag not in c.tags:
            continue
        if year is not None and c.local.year != year:
            continue
        out.append(c)
    return out


def params(**filters):
    """(zone, local_iso, expected_compatible_utc) tuples for pytest.mark.parametrize."""
    return [(c.zone, c.local.isoformat(), c.compatible) for c in cases(**filters)]


def check(func, policy="compatible", **filters):
    """Run func(zone, naive_local_datetime) -> aware datetime over the cases and return a list of
    (case, got) mismatches (empty list = all pass).

    policy "compatible": every case must return `compatible`.
    policy "earlier" / "later": overlaps must return that instant; gaps and normal cases are
    checked against `compatible` (most libraries shift gaps forward).
    policy "raise": gaps must raise any exception; others must return `compatible`.
    """
    if policy not in ("compatible", "earlier", "later", "raise"):
        raise ValueError("policy must be compatible, earlier, later or raise")
    bad = []
    for c in cases(**filters):
        want = c.compatible
        if c.kind == "overlap" and policy in ("earlier", "later"):
            want = getattr(c, policy)
        try:
            got = func(c.zone, c.local)
        except Exception as e:  # noqa: BLE001  (a gap may legitimately raise)
            if not (policy == "raise" and c.kind == "gap"):
                bad.append((c, e))
            continue
        if policy == "raise" and c.kind == "gap":
            bad.append((c, got))
        elif not isinstance(got, datetime) or got.tzinfo is None or got != want:
            bad.append((c, got))
    return bad


# ---- helpers on the local tz database (zoneinfo) --------------------------------------------

def _zi(zone):
    import zoneinfo
    return zoneinfo.ZoneInfo(zone)


def _naive(local):
    if isinstance(local, str):
        local = datetime.fromisoformat(local)
    if local.tzinfo is not None:
        raise ValueError("pass a naive local (wall clock) datetime")
    return local


def _wall(utc_dt, zi):
    return utc_dt.astimezone(zi).replace(tzinfo=None)


def to_utc(local, zone, fold=0):
    """Wall time in zone -> UTC with Python's rule (fold=0: offset before the change)."""
    return _naive(local).replace(tzinfo=_zi(zone), fold=fold).astimezone(_UTC)


def is_nonexistent(local, zone):
    """True if the wall time never appears on clocks in zone (spring-forward gap).
    Uses the tz database installed on this machine (or the `tzdata` package)."""
    local, zi = _naive(local), _zi(zone)
    return all(_wall(to_utc(local, zone, f), zi) != local for f in (0, 1))


def is_ambiguous(local, zone):
    """True if the wall time appears twice in zone (fall-back overlap)."""
    local = _naive(local)
    a, b = to_utc(local, zone, 0), to_utc(local, zone, 1)
    return a != b and not is_nonexistent(local, zone)


def _cli(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="dst-test-vectors",
                                description="List DST test vectors, or check this machine's tz database against them.")
    p.add_argument("--zone")
    p.add_argument("--kind", choices=KINDS)
    p.add_argument("--file", help="vectors JSON in the same format (default: bundled sample)")
    p.add_argument("--check", action="store_true",
                   help="check Python zoneinfo on this machine against the vectors (exit 1 on mismatch)")
    a = p.parse_args(argv)
    sel = cases(zone=a.zone, kind=a.kind, path=a.file)
    if a.check:
        bad = check(lambda z, l: to_utc(l, z), zone=a.zone, kind=a.kind, path=a.file)
        meta = load(a.file)[0]
        print(f"{len(sel) - len(bad)}/{len(sel)} cases match (vectors built from tzdata "
              f"{meta.get('tzdata_version')}; an older local tz database can differ)")
        for c, got in bad[:10]:
            print(f"MISMATCH {c.id}: expected {c.compatible.isoformat()}, got {got}")
        return 1 if bad else 0
    for c in sel:
        print(f"{c.zone}\t{c.local.isoformat()}\t{c.kind}\t{c.compatible.isoformat()}\t{','.join(c.tags)}")
    return 0


def cli():
    raise SystemExit(_cli())
