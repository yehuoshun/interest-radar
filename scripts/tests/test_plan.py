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

    def test_close_rows_feed_gate(self):
        """收尾打卡才是巡更间隔的起点：看了半小时才关掉，间隔从关掉那刻算。"""
        now = datetime(2026, 11, 13, 14, 3, tzinfo=p.TZ)
        self._log(now - timedelta(minutes=63))          # 13:00 开门，早过 50 分钟
        row = {"ts": (now - timedelta(minutes=23)).strftime("%Y-%m-%dT%H:%M:%S"),
               "delay_sec": 0, "kind": "close", "slept": False}
        with (self.dir / p.LOG_NAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        out = p.gate(now)
        self.assertFalse(out["allowed"])
        self.assertEqual(out["since_last_min"], 23)

    def test_wake_rrule_is_one_shot(self):
        """醒点写成一次性闹钟：FREQ=DAILY;COUNT=1，DTSTART 就是算出来的那一刻。"""
        wake = datetime(2026, 11, 13, 16, 42, tzinfo=p.TZ)
        r = p.wake_rrule(wake)
        self.assertEqual(r, "DTSTART;TZID=Asia/Shanghai:20261113T164200\nRRULE:FREQ=DAILY;COUNT=1")

    def test_pick_gap_min_in_range(self):
        """自己掷的间隔落在 50–120 分钟内，且多数不超过 90（三角分布，众数 60）。"""
        for _ in range(300):
            g = p.pick_gap_min()
            self.assertGreaterEqual(g, p.GAP_MIN)
            self.assertLessEqual(g, p.GAP_MAX_MIN)
        many = [p.pick_gap_min() for _ in range(300)]
        self.assertLess(sum(1 for g in many if g <= 75) / len(many), 1.0)
        self.assertGreater(sum(1 for g in many if g <= 75) / len(many), 0.4)

    def test_pick_gap_min_uses_triangular(self):
        """间隔走三角分布（不是均匀）：参数就是 50 / 120 / 60。"""
        seen = {}

        class Rng:
            def triangular(self, lo, hi, mode):
                seen.update(lo=lo, hi=hi, mode=mode)
                return 61.4

        self.assertEqual(p.pick_gap_min(Rng()), 61)
        self.assertEqual(seen, {"lo": 50, "hi": 120, "mode": 60})

    def test_next_wake_counts_from_close(self):
        """醒点 = 收尾那一刻 + 随机间隔（不按开门时间倒推）。"""
        now = datetime(2026, 11, 13, 15, 30, tzinfo=p.TZ)
        close = now - timedelta(minutes=3)
        row = {"ts": close.strftime("%Y-%m-%dT%H:%M:%S"), "delay_sec": 0,
               "kind": "close", "slept": False}
        with (self.dir / p.LOG_NAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        class Rng:
            def triangular(self, lo, hi, mode):
                return 74.0

        self.assertEqual(p.next_wake(now, Rng()),
                         datetime(2026, 11, 13, 16, 41, tzinfo=p.TZ))

    def test_next_wake_never_in_the_past(self):
        """锚点太久远时不能算出过去的时间（那等于立刻再开一串）。"""
        now = datetime(2026, 11, 13, 15, 30, tzinfo=p.TZ)
        self._log(now - timedelta(hours=5))

        class Rng:
            def triangular(self, lo, hi, mode):
                return 50.0

        self.assertEqual(p.next_wake(now, Rng()),
                         datetime(2026, 11, 13, 15, 31, tzinfo=p.TZ))

    def test_pick_gap_min_stays_in_range(self):
        """随机间隔始终落在 50–120 分钟（护栏 50 起，最多两小时）。"""
        for _ in range(300):
            g = p.pick_gap_min()
            self.assertGreaterEqual(g, p.GAP_MIN)
            self.assertLessEqual(g, p.GAP_MAX_MIN)

    def test_pick_gap_min_uses_triangular(self):
        """间隔用三角分布掷（50/120 为界，众数 60），不是均匀随机。"""
        seen = {}

        class Rng:
            def triangular(self, low, high, mode):
                seen["bounds"] = (low, high, mode)
                return 60.4

        self.assertEqual(p.pick_gap_min(Rng()), 60)
        self.assertEqual(seen["bounds"], (50, 120, 60))

    def test_next_wake_from_close_anchor(self):
        """醒点 = 上一次收尾 + 随机间隔：15:27 收尾、掷出 74 分钟 → 16:41。"""
        now = datetime(2026, 11, 13, 15, 30, tzinfo=p.TZ)
        self._log(now - timedelta(minutes=3))

        class Rng:
            def triangular(self, low, high, mode):
                return 74

        self.assertEqual(p.next_wake(now, Rng()), datetime(2026, 11, 13, 16, 41, tzinfo=p.TZ))

    def test_next_wake_never_in_past(self):
        """算出来的醒点已经在过去（比如隔了很久才想起）→ 顺延到下一分钟，不排一个过去的闹钟。"""
        now = datetime(2026, 11, 13, 15, 30, tzinfo=p.TZ)
        self._log(now - timedelta(hours=5))

        class Rng:
            def triangular(self, low, high, mode):
                return 50

        self.assertEqual(p.next_wake(now, Rng()), datetime(2026, 11, 13, 15, 31, tzinfo=p.TZ))

    def test_rrule_has_planned_hours(self):
        r = p.rrule(datetime(2026, 11, 13, 14, 3, tzinfo=p.TZ))
        self.assertIn("BYMINUTE=0", r)
        self.assertIn("BYHOUR=" + ",".join(str(h) for h in range(24)), r)
        self.assertTrue(r.startswith("DTSTART;TZID=Asia/Shanghai:20261113T150000"))


if __name__ == "__main__":
    unittest.main()
