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
        (self.dir / p.LOG_NAME).write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_hours_match_cadence(self):
        self.assertEqual(p.hours(), sorted(p.DAY_HOURS + p.NIGHT_HOURS))
        self.assertNotIn(6, p.hours())          # 睡觉时间不排班
        self.assertNotIn(7, p.hours())
        self.assertTrue(p.is_night(23) and p.is_night(3))
        self.assertFalse(p.is_night(12))

    def test_gap_by_period(self):
        self.assertEqual(p.required_gap(2), p.NIGHT_GAP_MIN)
        self.assertEqual(p.required_gap(15), p.DAY_GAP_MIN)

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
        self._log(now - timedelta(minutes=p.DAY_GAP_MIN + 5))
        self.assertTrue(p.gate(now)["allowed"])

    def test_rrule_has_planned_hours(self):
        r = p.rrule(datetime(2026, 11, 13, 14, 3, tzinfo=p.TZ))
        self.assertIn("BYMINUTE=0", r)
        self.assertIn("BYHOUR=0,1,2,3,4,5,8,10,12,14,16,18,20,22,23", r)
        self.assertTrue(r.startswith("DTSTART;TZID=Asia/Shanghai:"))


if __name__ == "__main__":
    unittest.main()
