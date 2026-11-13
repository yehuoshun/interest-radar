# -*- coding: utf-8 -*-
"""test_schedule.py —— 调度模式翻译成 rrule（DSH 的 rrule 子集）。"""
import unittest

import schedule as sched


class TestIntervalRrule(unittest.TestCase):
    def test_minutely_interval_has_no_by_parts(self):
        r = sched.build_interval_rrule(10)
        self.assertIn("RRULE:FREQ=MINUTELY;INTERVAL=10", r)
        # DSH 的 rrule 子集里 MINUTELY 不接受 BY 部件
        self.assertNotIn("BYHOUR", r)
        self.assertNotIn("BYMINUTE", r)
        self.assertEqual(len(r.splitlines()), 2)
        self.assertTrue(r.splitlines()[0].startswith("DTSTART;TZID=Asia/Shanghai:"))

    def test_start_aligned_to_slot(self):
        r = sched.build_interval_rrule(10)
        stamp = r.splitlines()[0].split(":")[-1]
        self.assertEqual(len(stamp), 15, stamp)          # YYYYMMDDTHHMMSS
        self.assertEqual(int(stamp[-2:]) % 10, 0, stamp)  # 对齐到 10 分钟格点

    def test_out_of_range_rejected(self):
        for bad in (0, 4, 1441):
            with self.assertRaises(ValueError):
                sched.build_interval_rrule(bad)

    def test_interval_mode_roundtrip(self):
        self.assertEqual(sched.interval_mode(10), "every10m")
        m = sched.INTERVAL_MODE_RE.match("every10m")
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 10)
        self.assertIsNone(sched.INTERVAL_MODE_RE.match("valley"))

    def test_plan_dispatches_by_mode(self):
        self.assertIn("INTERVAL=10", sched.plan("every10m"))
        self.assertIn("FREQ=DAILY", sched.plan("all", 17))
        self.assertIn("BYMINUTE=17", sched.plan("valley", 17))


class TestDailyRrule(unittest.TestCase):
    def test_valley_hours(self):
        r = sched.build_rrule("valley", 17)
        self.assertIn("BYHOUR=0,1,2,3,4,5,6,7,8,12,13,18,19,20,21,22,23", r)
        self.assertIn("BYMINUTE=17", r)

    def test_all_hours(self):
        r = sched.build_rrule("all", 17)
        self.assertIn("BYHOUR=" + ",".join(str(h) for h in range(24)), r)

    def test_night_shift_excludes_daytime(self):
        r = sched.build_rrule("night", 43)
        self.assertIn("BYHOUR=0,1,2,3,4,5,22,23", r)
        # 白天不排班：9-21 点一个都不许出现
        for h in range(6, 22):
            self.assertNotIn(f"={h},", r)
            self.assertNotIn(f",{h},", r)
        self.assertIn("BYMINUTE=43", r)


class TestRandomMinute(unittest.TestCase):
    """随机拨钟：分钟在范围内、下一次触发至少留出提前量。"""

    def test_pick_minute_in_range(self):
        picks = [sched.pick_minute() for _ in range(200)]
        self.assertTrue(all(sched.MINUTE_LO <= m <= sched.MINUTE_HI for m in picks), picks[:10])
        self.assertGreater(len(set(picks)), 5)          # 真随机，不是常数

    def test_pick_minute_rejects_bad_range(self):
        with self.assertRaises(ValueError):
            sched.pick_minute(58, 2)
        with self.assertRaises(ValueError):
            sched.pick_minute(-1, 30)

    def test_lead_minutes_pushes_next_slot(self):
        import re
        from datetime import datetime

        r = sched.build_rrule("all", 30, lead_minutes=25)
        stamp = r.splitlines()[0].split(":")[-1]
        start = datetime.strptime(stamp, "%Y%m%dT%H%M%S").replace(tzinfo=sched.TZ)
        now = datetime.now(sched.TZ)
        self.assertGreaterEqual((start - now).total_seconds(), 24 * 60, r)
        self.assertIn("BYMINUTE=30", r)
        self.assertTrue(re.search(r"BYHOUR=0,1,", r))


if __name__ == "__main__":
    unittest.main()
