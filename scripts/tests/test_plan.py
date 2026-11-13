# -*- coding: utf-8 -*-
"""test_plan.py —— 值班节奏（排班整点 / 护栏间隔 / 该不该刷 / rrule）。"""
import json
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta

import plan as p


class TestPlan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = pathlib.Path(self._tmp.name)
        self._orig = p.state_dir
        p.state_dir = lambda: self.dir
        self.addCleanup(lambda: setattr(p, "state_dir", self._orig))

    def _log(self, moment):
        row = {"ts": moment.strftime("%Y-%m-%dT%H:%M:%S"), "delay_sec": 30, "max_min": 10, "slept": True}
        with (self.dir / p.LOG_NAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _rest(self, moment):
        row = {"ts": moment.strftime("%Y-%m-%dT%H:%M:%S"), "delay_sec": 180, "max_min": 10,
               "min_min": 1, "kind": "rest", "slept": True}
        with (self.dir / p.LOG_NAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_hours_all_day(self):
        """全天每小时一巡（14:02 老板选「2」）：24 个整点，没有睡觉窗口。"""
        self.assertEqual(p.hours(), list(range(24)))
        self.assertIn(6, p.hours())
        self.assertIn(7, p.hours())

    def test_gap_is_flat(self):
        """护栏只有一个值（50 分钟），不再分白天/夜里。"""
        self.assertEqual(p.GAP_MIN, 50)
        self.assertFalse(hasattr(p, "DAY_GAP_MIN"))
        self.assertFalse(hasattr(p, "NIGHT_GAP_MIN"))

    def test_next_hour_is_next_whole_hour(self):
        nxt = p.next_hour(datetime(2026, 11, 13, 14, 3, tzinfo=p.TZ))
        self.assertEqual(nxt, datetime(2026, 11, 13, 15, 0, tzinfo=p.TZ))
        nxt2 = p.next_hour(datetime(2026, 11, 13, 23, 59, tzinfo=p.TZ))
        self.assertEqual(nxt2, datetime(2026, 11, 14, 0, 0, tzinfo=p.TZ))

    def test_gate_allows_first_scan(self):
        now = datetime(2026, 11, 13, 14, 3, tzinfo=p.TZ)
        out = p.gate(now)
        self.assertTrue(out["allowed"])
        self.assertIsNone(out["since_last_min"])

    def test_gate_blocks_too_soon(self):
        now = datetime(2026, 11, 13, 14, 3, tzinfo=p.TZ)
        self._log(now - timedelta(minutes=40))
        out = p.gate(now)
        self.assertFalse(out["allowed"])
        self.assertEqual(out["since_last_min"], 40)
        self.assertIn("静默", out["reason"])

    def test_gate_allows_after_gap(self):
        now = datetime(2026, 11, 13, 14, 3, tzinfo=p.TZ)
        self._log(now - timedelta(minutes=p.GAP_MIN + 5))
        self.assertTrue(p.gate(now)["allowed"])

    def test_rest_rows_do_not_feed_gate(self):
        """串内歇息不能喂饱巡更护栏：刚歇完也算「该刷」。"""
        now = datetime(2026, 11, 13, 14, 3, tzinfo=p.TZ)
        self._log(now - timedelta(minutes=p.GAP_MIN + 20))
        self._rest(now - timedelta(minutes=1))
        out = p.gate(now)
        self.assertTrue(out["allowed"])
        self.assertEqual(out["since_last_min"], p.GAP_MIN + 20)

    def test_rrule_has_planned_hours(self):
        r = p.rrule(datetime(2026, 11, 13, 14, 3, tzinfo=p.TZ))
        self.assertIn("BYMINUTE=0", r)
        self.assertIn("BYHOUR=" + ",".join(str(h) for h in range(24)), r)
        self.assertTrue(r.startswith("DTSTART;TZID=Asia/Shanghai:20261113T150000"))


if __name__ == "__main__":
    unittest.main()
