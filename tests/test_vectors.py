"""Check dst_test_vectors.json with Python zoneinfo (fold=0 / fold=1) and round-trips.
Also a template for your own code: replace `to_utc` with your function.
Run: python3 tests/test_vectors.py"""
import json, os, unittest, zoneinfo
from datetime import datetime, timezone

# Uses your system tz database (or the `tzdata` package). Results can differ if its version is older than the vectors'.
HERE = os.path.dirname(os.path.abspath(__file__))
V = json.load(open(os.path.join(HERE, "..", "sample", "dst_test_vectors_sample.json"), encoding="utf-8"))
UTC = timezone.utc


def z(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def to_utc(zone, local, fold):
    return datetime.fromisoformat(local).replace(tzinfo=zoneinfo.ZoneInfo(zone), fold=fold).astimezone(UTC)


class Vectors(unittest.TestCase):
    def test_cases(self):
        bad = []
        for c in V["cases"]:
            zi = zoneinfo.ZoneInfo(c["zone"])
            got0 = to_utc(c["zone"], c["local"], 0)
            if got0 != z(c["compatible_utc"]):
                bad.append(("compatible", c)); continue
            if c["ambiguous"]:
                if to_utc(c["zone"], c["local"], 1) != z(c["utc_later"]) or got0 != z(c["utc_earlier"]):
                    bad.append(("ambiguous", c))
                for k in ("utc_earlier", "utc_later"):  # both instants show the same wall time
                    if z(c[k]).astimezone(zi).replace(tzinfo=None).isoformat() != c["local"]:
                        bad.append(("roundtrip", c))
            elif not c["exists"]:
                # no instant shows this wall time
                for k in ("utc_if_offset_before", "utc_if_offset_after"):
                    if z(c[k]).astimezone(zi).replace(tzinfo=None).isoformat() == c["local"]:
                        bad.append(("gap-exists", c))
            else:
                if z(c["utc"]).astimezone(zi).replace(tzinfo=None).isoformat() != c["local"]:
                    bad.append(("unique", c))
        self.assertEqual(bad[:3], [])
        self.assertGreater(len(V["cases"]), 10)


if __name__ == "__main__":
    unittest.main()
