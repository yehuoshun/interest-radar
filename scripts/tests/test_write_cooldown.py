"""写冷却：间隔不足 die / 干跑不查（函数不含干跑逻辑，只测函数本体）/ 删动态豁免在调用方。"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from radar_lib import cli as R


class TestWriteCooldown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["INTERESTS_DIR"] = self.tmp

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def _log(self, ts, fname="write-log.jsonl"):
        Path(self.tmp, fname).write_text(
            json.dumps({"ts": ts.isoformat(), "kind": "comment"}) + "\n", encoding="utf-8")

    def test_blocks_when_recent(self):
        self._log(datetime.now() - timedelta(seconds=5))
        with self.assertRaises(SystemExit) as cm:
            R._write_cooldown(Path(self.tmp), 120)
        self.assertEqual(cm.exception.code, 12)

    def test_passes_after_gap(self):
        self._log(datetime.now() - timedelta(seconds=300))
        R._write_cooldown(Path(self.tmp), 120)  # 不抛即过

    def test_passes_with_no_log(self):
        R._write_cooldown(Path(self.tmp), 120)

    def test_checks_mention_log_too(self):
        """mention-log 里的最近写入也要算。"""
        self._log(datetime.now() - timedelta(seconds=3), fname="mention-log.jsonl")
        with self.assertRaises(SystemExit):
            R._write_cooldown(Path(self.tmp), 120)

    def test_takes_latest_of_both_logs(self):
        self._log(datetime.now() - timedelta(seconds=500))  # 旧
        self._log(datetime.now() - timedelta(seconds=10), fname="mention-log.jsonl")  # 新
        with self.assertRaises(SystemExit):
            R._write_cooldown(Path(self.tmp), 120)


if __name__ == "__main__":
    unittest.main()