# -*- coding: utf-8 -*-
"""test_jitter.py —— 巡更抖动（分布范围 / 干跑不睡 / 越界拒绝 / 落账本）。"""
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

    def _args(self, max_min=12, sleep=False):
        return types.SimpleNamespace(max_min=max_min, sleep=sleep)

    def _run(self, a):
        buf = io.StringIO()
        with redirect_stdout(buf):
            j.cmd_jitter(a)
        return json.loads(buf.getvalue())

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
        rows = [json.loads(x) for x in (self.dir / "jitter-log.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["delay_sec"], out["delay_sec"])

    def test_out_of_range_rejected(self):
        for bad in (-1, 61):
            with self.assertRaises(SystemExit):
                self._run(self._args(max_min=bad))


if __name__ == "__main__":
    unittest.main()
