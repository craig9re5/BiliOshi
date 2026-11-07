import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bilioshi.growth import growth_path, load_history, record_samples

TZ = timezone(timedelta(hours=8))


def ts(year, month, day, hour=12, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TZ).timestamp()


def members(*rows):
    return [
        {"name": name, "uid": uid, "room": room}
        for name, uid, room in rows
    ]


class GrowthRecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.now = ts(2026, 11, 7, 18)
        self.today = "2026-11-07"
        self.people = members(("嘉然", 1, 10), ("贝拉", 2, 20))

    def tearDown(self):
        self.directory.cleanup()

    def record(self, observed_at, medals, *, account="uid-1", people=None, now=None):
        return record_samples(
            self.root, account, people if people is not None else self.people,
            medals, observed_at, now=now if now is not None else self.now,
        )

    def history(self, *, account="uid-1", days=7, people=None, now=None):
        return load_history(
            self.root, account, days,
            members=people if people is not None else self.people,
            now=now if now is not None else self.now,
        )

    def test_daily_max_and_recorded_zero(self):
        self.assertTrue(self.record(ts(2026, 11, 7, 12), {
            1: {"today_intimacy": 10, "medal_name": "小草莓", "level": 9, "day_limit": 1500},
            2: {"today_intimacy": 0},
        }))
        self.assertTrue(self.record(ts(2026, 11, 7, 13), {
            1: {"today_intimacy": 15},
            2: {"today_intimacy": None},
        }))
        data = self.history()
        self.assertTrue(data["available"])
        rooms = {row["room"]: row for row in data["rooms"]}
        first = rooms[10]
        self.assertEqual(first["recorded_days"], 1)
        self.assertEqual(first["recorded_total"], 15)
        self.assertEqual(first["cells"][-1]["value"], 15)
        self.assertEqual(first["cells"][-1]["samples"], 2)
        self.assertEqual(rooms[20]["cells"][-1]["value"], 0)
        self.assertTrue(rooms[20]["cells"][-1]["recorded"])
        self.assertEqual(data["coverage"][self.today]["rooms_recorded"], 2)
        self.assertEqual(data["coverage"][self.today]["rooms_recordable"], 2)
        self.assertTrue(data["coverage"][self.today]["partial"])

    def test_missing_medal_is_not_zero(self):
        self.assertFalse(self.record(ts(2026, 11, 7, 12), {}))
        self.assertFalse(growth_path(self.root).exists())
        data = self.history()
        self.assertTrue(data["available"])
        rooms = {row["room"]: row for row in data["rooms"]}
        self.assertFalse(rooms[10]["cells"][-1]["recorded"])
        self.assertIsNone(rooms[10]["cells"][-1]["value"])
        self.assertEqual(data["coverage"][self.today]["rooms_recorded"], 0)

    def test_invalid_values_are_skipped(self):
        for value in (None, True, False, -1, "10", 10.5):
            self.assertFalse(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": value}}))
        self.assertFalse(growth_path(self.root).exists())

    def test_corrupt_file_is_never_overwritten(self):
        path = growth_path(self.root)
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        before = path.read_bytes()
        self.assertFalse(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": 10}}))
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.history()["available"])

    def test_unknown_version_fails_closed(self):
        path = growth_path(self.root)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"version": 99, "days": {}}), encoding="utf-8")
        self.assertFalse(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": 10}}))
        data = self.history()
        self.assertFalse(data["available"])
        self.assertIn("版本", data["error"])

    def test_account_mismatch_fails_closed(self):
        self.assertTrue(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": 10}}))
        data = self.history(account="uid-2")
        self.assertFalse(data["available"])

    def test_duplicate_uid_records_once(self):
        people = members(("A", 1, 10), ("A again", 1, 20))
        self.assertTrue(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": 7}}, people=people))
        data = self.history(people=people)
        rooms = {row["room"]: row for row in data["rooms"]}
        self.assertTrue(rooms[10]["cells"][-1]["recorded"])
        self.assertFalse(rooms[20]["cells"][-1]["recorded"])

    def test_clock_rollback_does_not_rewrite_history(self):
        self.assertTrue(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": 50}}))
        self.assertFalse(self.record(ts(2026, 11, 6, 12), {1: {"today_intimacy": 99}}))
        data = self.history(days=2)
        rooms = {row["room"]: row for row in data["rooms"]}
        self.assertEqual(rooms[10]["cells"][-1]["value"], 50)
        self.assertIsNone(rooms[10]["cells"][0]["value"])

    def test_cross_midnight_uses_observation_day(self):
        observed = ts(2026, 11, 7, 23, 59)
        after = ts(2026, 11, 8, 0, 1)
        self.assertTrue(self.record(observed, {1: {"today_intimacy": 42}}, now=after))
        data = self.history(days=2, now=after)
        self.assertEqual(data["today"], "2026-11-08")
        rooms = {row["room"]: row for row in data["rooms"]}
        self.assertEqual(rooms[10]["cells"][0]["value"], 42)
        self.assertIsNone(rooms[10]["cells"][1]["value"])

    def test_retention_prunes_old_days(self):
        self.assertTrue(self.record(
            ts(2026, 8, 1, 12), {1: {"today_intimacy": 5}}, now=ts(2026, 8, 1, 18),
        ))
        self.assertTrue(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": 10}}))
        raw = json.loads(growth_path(self.root).read_text(encoding="utf-8"))
        self.assertNotIn("2026-08-01", raw["days"])
        self.assertIn("2026-11-07", raw["days"])

    def test_load_shape_and_missing_file(self):
        data = self.history()
        self.assertTrue(data["available"])
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual(data["days"][-1], self.today)
        self.assertEqual(len(data["rooms"]), 2)
        for row in data["rooms"]:
            self.assertEqual(len(row["cells"]), 7)
            self.assertEqual([cell["day"] for cell in row["cells"]], data["days"])
        self.assertEqual(set(data["coverage"]), set(data["days"]))

    def test_partial_day_uses_last_observation(self):
        self.assertTrue(self.record(ts(2026, 11, 6, 12), {1: {"today_intimacy": 3}}))
        self.assertTrue(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": 10}}))
        data = self.history(days=2)
        self.assertTrue(data["coverage"]["2026-11-06"]["partial"])
        self.assertTrue(data["coverage"]["2026-11-07"]["partial"])

    def test_current_member_name_wins(self):
        self.assertTrue(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": 10}}))
        people = members(("新名字", 1, 10))
        data = self.history(people=people)
        self.assertEqual(data["rooms"][0]["name"], "新名字")

    def test_removed_member_keeps_history(self):
        self.assertTrue(self.record(ts(2026, 11, 7, 12), {1: {"today_intimacy": 10}}))
        data = self.history(people=[])
        self.assertEqual(len(data["rooms"]), 1)
        self.assertFalse(data["rooms"][0]["tracked"])
        self.assertEqual(data["rooms"][0]["name"], "嘉然")
        self.assertEqual(data["rooms"][0]["cells"][-1]["value"], 10)
        self.assertEqual(data["coverage"][self.today]["rooms_recordable"], 0)

    def test_days_validation(self):
        for value in (0, 91, True, "7", None):
            with self.assertRaises(ValueError):
                load_history(self.root, "uid-1", value, members=self.people, now=self.now)


if __name__ == "__main__":
    unittest.main()
