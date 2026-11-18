"""Tests for the dst-test-vectors package (src/dst_test_vectors). Run: PYTHONPATH=src python3 -m unittest discover -s tests"""
import filecmp, io, os, sys, unittest, zoneinfo
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import dst_test_vectors as dtv  # noqa: E402

UTC = timezone.utc


def py_to_utc(zone, local):
    return local.replace(tzinfo=zoneinfo.ZoneInfo(zone)).astimezone(UTC)


class Data(unittest.TestCase):
    def test_bundled_copy_matches_repo_sample(self):
        self.assertTrue(filecmp.cmp(os.path.join(HERE, "..", "sample", "dst_test_vectors_sample.json"),
                                    os.path.join(HERE, "..", "src", "dst_test_vectors", "data", "sample.json"),
                                    shallow=False))

    def test_counts_and_kinds(self):
        self.assertEqual(len(dtv.cases()), 36)
        self.assertEqual(len(dtv.cases(kind="gap")), 10)
        self.assertEqual(len(dtv.cases(kind="overlap")), 8)
        self.assertEqual(len(dtv.cases(kind="normal")), 18)
        self.assertEqual(dtv.TZDATA_VERSION, "2026f")
        self.assertEqual({c.zone for c in dtv.cases()},
                         {"America/New_York", "Europe/London", "America/Havana", "Australia/Lord_Howe", "Pacific/Chatham"})

    def test_filters(self):
        self.assertTrue(all(c.zone == "Australia/Lord_Howe" for c in dtv.cases(zone="Australia/Lord_Howe")))
        self.assertTrue(dtv.cases(tag="delta_30min"))
        self.assertTrue(all("midnight" in c.tags for c in dtv.cases(tag="midnight")))
        self.assertEqual(dtv.cases(year=1999), [])
        self.assertEqual(dtv.cases(zone=[]), [])
        self.assertEqual(len(dtv.cases(zone=["Europe/London", "America/New_York"])),
                         len(dtv.cases(zone="Europe/London")) + len(dtv.cases(zone="America/New_York")))
        with self.assertRaises(ValueError):
            dtv.cases(kind="fold")

    def test_case_invariants(self):
        for c in dtv.cases():
            self.assertLessEqual(c.earlier, c.later, c)
            self.assertIn(c.compatible, (c.earlier, c.later), c)
            if c.kind == "overlap":
                self.assertEqual(c.compatible, c.earlier, c)  # compatible = earlier instant in an overlap
            if c.kind == "gap":
                self.assertEqual(c.compatible, c.later, c)    # = offset before the change = later instant
                self.assertEqual(c.compatible, dtv._z(c.raw["utc_if_offset_before"]))

    def test_params(self):
        p = dtv.params(kind="overlap")
        self.assertEqual(len(p), 8)
        self.assertIsInstance(p[0][1], str)


class Check(unittest.TestCase):
    """Run with PyPI tzdata 2026.6 (= IANA 2026f) and PYTHONTZPATH="" as in CI."""

    def test_python_zoneinfo_passes(self):
        self.assertEqual(dtv.check(py_to_utc), [])

    def test_later_policy_with_fold1(self):
        f = lambda z, l: l.replace(tzinfo=zoneinfo.ZoneInfo(z), fold=1).astimezone(UTC)  # noqa: E731
        bad = dtv.check(f, policy="later")
        self.assertTrue(bad)  # fold=1 also moves gaps the other way: those must be reported
        self.assertTrue(all(c.kind == "gap" for c, _ in bad))

    def test_detects_naive_utc_bug(self):
        # Classic bug: treat local time as a fixed standard offset.
        def buggy(zone, local):
            off = zoneinfo.ZoneInfo(zone).utcoffset(datetime(local.year, 1, 15))
            return (local - off).replace(tzinfo=UTC)
        self.assertTrue(dtv.check(buggy))

    def test_raise_policy(self):
        def strict(zone, local):
            if dtv.is_nonexistent(local, zone):
                raise ValueError("nonexistent")
            return py_to_utc(zone, local)
        self.assertEqual(dtv.check(strict, policy="raise"), [])
        self.assertTrue(dtv.check(py_to_utc, policy="raise"))  # does not raise on gaps
        self.assertTrue(dtv.check(strict))  # compatible policy: raising is a failure

    def test_naive_result_is_failure(self):
        self.assertEqual(len(dtv.check(lambda z, l: l)), 36)
        self.assertEqual(len(dtv.check(lambda z, l: l.isoformat())), 36)  # wrong type is reported, not raised


class Helpers(unittest.TestCase):
    def test_against_vectors(self):
        for c in dtv.cases():
            self.assertEqual(dtv.is_nonexistent(c.local, c.zone), c.kind == "gap", c)
            self.assertEqual(dtv.is_ambiguous(c.local, c.zone), c.kind == "overlap", c)
            self.assertEqual(dtv.to_utc(c.local, c.zone), c.compatible, c)

    def test_known_examples(self):
        self.assertTrue(dtv.is_nonexistent("2026-03-08T02:30:00", "America/New_York"))
        self.assertTrue(dtv.is_ambiguous("2026-11-01T01:30:00", "America/New_York"))
        self.assertFalse(dtv.is_ambiguous("2026-11-01T03:00:00", "America/New_York"))
        self.assertFalse(dtv.is_nonexistent("2026-07-01T12:00:00", "Asia/Kolkata"))
        self.assertEqual(dtv.to_utc("2026-11-01T01:30:00", "America/New_York", fold=1),
                         datetime(2026, 11, 1, 6, 30, tzinfo=UTC))
        with self.assertRaises(ValueError):
            dtv.is_ambiguous(datetime(2026, 1, 1, tzinfo=UTC), "UTC")

    def test_random_hours_new_york(self):
        # Every hour of 2026: exactly the 1:xx hour on Nov 1 is ambiguous and 2:xx on Mar 8 is nonexistent.
        t, amb, gap = datetime(2026, 1, 1, 0, 30), [], []
        while t.year == 2026:
            if dtv.is_ambiguous(t, "America/New_York"):
                amb.append(t)
            if dtv.is_nonexistent(t, "America/New_York"):
                gap.append(t)
            t += timedelta(hours=1)
        self.assertEqual(amb, [datetime(2026, 11, 1, 1, 30)])
        self.assertEqual(gap, [datetime(2026, 3, 8, 2, 30)])


class CLI(unittest.TestCase):
    def test_list_and_check(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(dtv._cli(["--zone", "Pacific/Chatham", "--kind", "gap"]), 0)
        lines = buf.getvalue().strip().splitlines()
        self.assertTrue(lines and all(l.startswith("Pacific/Chatham\t") and "\tgap\t" in l for l in lines))
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(dtv._cli(["--check"]), 0)
        self.assertIn("36/36 cases match", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
