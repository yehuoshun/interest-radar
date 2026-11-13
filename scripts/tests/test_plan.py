# -*- coding: utf-8 -*-
"""test_plan.py —— 节奏只有一条：上一次观看结束 + 1–10 分钟，下次观看开始。"""
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

    def _log(self, moment, kind="open"):
        row = {"ts": moment.strftime("%Y-%m-%dT%H:%M:%S"), "delay_sec": 30,
               "max_min": 10, "slept": True}
        if kind != "open":
            row["kind"] = kind
        with (self.dir / p.LOG_NAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_rest_bounds_are_one_to_ten(self):
        """歇息区间就是老板说的 1–10 分钟，没有第二套间隔。"""
        self.assertEqual((p.REST_MIN, p.REST_MAX), (1, 10))
        for _ in range(300):
            v = p.rest_min()
            self.assertGreaterEqual(v, 1)
            self.assertLessEqual(v, 10)

    def test_rest_min_uses_randint(self):
        """歇息用整数分钟均匀掷（不是三角分布、不是 50–120 那种拍的区间）。"""
        seen = {}

        class Rng:
            def randint(self, low, high):
                seen["bounds"] = (low, high)
                return 7

        self.assertEqual(p.rest_min(Rng()), 7)
        self.assertEqual(seen["bounds"], (1, 10))

    def test_last_seen_counts_every_kind(self):
        """开门、歇息、收尾都算「还在 B 站」：节奏是连续的，不分串内串外。"""
        now = datetime(2026, 11, 13, 16, 30, tzinfo=p.TZ)
        self._log(now - timedelta(minutes=40), "open")
        self._log(now - timedelta(minutes=30), "rest")
        self._log(now - timedelta(minutes=12), "close")
        self.assertEqual(p.last_seen(), now - timedelta(minutes=12))

    def test_next_wake_is_last_seen_plus_rest(self):
        """醒点 = 上一次记录 + 掷出来的 1–10 分钟（16:18 收尾 + 4 分钟 → 16:22）。"""
        now = datetime(2026, 11, 13, 16, 20, tzinfo=p.TZ)
        self._log(now - timedelta(minutes=2), "close")

        class Rng:
            def randint(self, low, high):
                return 4

        self.assertEqual(p.next_wake(now, Rng()), datetime(2026, 11, 13, 16, 22, tzinfo=p.TZ))

    def test_next_wake_never_in_past(self):
        """算出来已经过去的醒点（比如隔了很久才想起）→ 顺延到下一分钟，不排过去的闹钟。"""
        now = datetime(2026, 11, 13, 16, 20, tzinfo=p.TZ)
        self._log(now - timedelta(hours=5), "close")

        class Rng:
            def randint(self, low, high):
                return 3

        self.assertEqual(p.next_wake(now, Rng()), datetime(2026, 11, 13, 16, 21, tzinfo=p.TZ))

    def test_wake_rrule_is_one_shot(self):
        """醒点写成一次性闹钟：FREQ=DAILY;COUNT=1，DTSTART 就是算出来的那一刻。"""
        wake = datetime(2026, 11, 13, 16, 22, tzinfo=p.TZ)
        self.assertEqual(p.wake_rrule(wake),
                         "DTSTART;TZID=Asia/Shanghai:20261113T162200\nRRULE:FREQ=DAILY;COUNT=1")

    def test_gate_skips_same_minute(self):
        """同一分钟内重复触发就跳过（只防抖）；隔了 ≥1 分钟照常开刷。"""
        now = datetime(2026, 11, 13, 16, 30, tzinfo=p.TZ)
        self.assertTrue(p.gate(now)["allowed"])          # 没有记录
        self._log(now, "close")
        out = p.gate(now)
        self.assertFalse(out["allowed"])
        self.assertEqual(out["since_last_min"], 0)
        self.assertTrue(p.gate(now + timedelta(minutes=2))["allowed"])


if __name__ == "__main__":
    unittest.main()
