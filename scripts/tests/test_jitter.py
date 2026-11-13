# -*- coding: utf-8 -*-
"""test_jitter.py —— 抖动/歇息（分布范围 / 干跑不睡 / 越界拒绝 / 落账本 / kind）。"""
import io
import json
import pathlib
import tempfile
import time
import types
import unittest
from contextlib import redirect_stdout

from bili_radar import jitter as j


class TestJitter(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = pathlib.Path(self._tmp.name)
        self._orig = j.state_dir
        j.state_dir = lambda: self.dir
        self.addCleanup(lambda: setattr(j, "state_dir", self._orig))

    def _args(self, max_min=12, sleep=False, min_min=0, rest=False):
        return types.SimpleNamespace(max_min=max_min, min_min=min_min, rest=rest, sleep=sleep)

    def _run(self, a):
        buf = io.StringIO()
        with redirect_stdout(buf):
            j.cmd_jitter(a)
        return json.loads(buf.getvalue())

    def _rows(self):
        return [json.loads(x) for x in
                (self.dir / "jitter-log.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_delay_within_bounds(self):
        for mx in (0, 1, 12):
            for _ in range(20):
                sec = j.pick_delay(mx)
                self.assertGreaterEqual(sec, 0)
                self.assertLessEqual(sec, mx * 60)

    def test_dry_run_does_not_sleep_and_logs(self):
        t0 = time.time()
        out = self._run(self._args())
        self.assertLess(time.time() - t0, 1.0)
        self.assertFalse(out["slept"])
        self.assertLessEqual(out["delay_sec"], 12 * 60)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["delay_sec"], out["delay_sec"])
        self.assertEqual(rows[0]["kind"], "open")

    def test_out_of_range_rejected(self):
        for bad in (-1, 61):
            with self.assertRaises(SystemExit):
                self._run(self._args(max_min=bad))

    def test_rest_has_floor(self):
        """串内歇息 1–10 分钟：下限真的生效（11-13 老板「歇 1–10 分钟」）。"""
        for _ in range(50):
            sec = j.pick_delay(10, 1)
            self.assertGreaterEqual(sec, 60)
            self.assertLessEqual(sec, 600)

    def test_rest_logged_with_kind(self):
        out = self._run(self._args(max_min=10, min_min=1, rest=True))
        self.assertEqual(out["kind"], "rest")
        row = self._rows()[0]
        self.assertEqual(row["kind"], "rest")
        self.assertEqual(row["min_min"], 1)
        self.assertGreaterEqual(row["delay_sec"], 60)

    def test_min_greater_than_max_rejected(self):
        with self.assertRaises(SystemExit):
            self._run(self._args(max_min=3, min_min=9))


if __name__ == "__main__":
    unittest.main()
