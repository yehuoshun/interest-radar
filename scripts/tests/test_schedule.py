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


if __name__ == "__main__":
    unittest.main()
