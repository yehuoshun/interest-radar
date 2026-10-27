"""engagement：活跃 / 纯沉默 / 故障 三分支。"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bili_radar import cli as R


class TestEngagement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["INTERESTS_DIR"] = self.tmp
        (Path(self.tmp) / "out").mkdir()

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def _report(self, days_ago=0):
        d = datetime.now() - timedelta(days=days_ago)
        (Path(self.tmp) / "out" / (d.strftime("%Y-%m-%d") + ".md")).write_text("x")

    def _evidence(self, days_ago=3):
        with (Path(self.tmp) / "evidence.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": (datetime.now() - timedelta(days=days_ago))
                                .isoformat(), "topic": "t", "signal": "like"}) + "\n")

    def _mention_replied(self, days_ago=3):
        with (Path(self.tmp) / "mention-log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": (datetime.now() - timedelta(days=days_ago))
                                .isoformat(), "bv": "BV1", "rpid": "1", "kind": "replied"}) + "\n")

    def _run(self, days=14):
        a = SimpleNamespace(days=days)
        captured = {}
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            R.cmd_engagement(a)
        captured = json.loads(buf.getvalue())
        return captured

    def test_active_with_feedback(self):
        self._report()
        self._evidence()
        out = self._run()
        self.assertEqual(out["报告数"], 1)
        self.assertEqual(out["老板反馈"], 1)
        self.assertIn("活跃", out["verdict"])

    def test_active_with_owner_at(self):
        self._report()
        self._mention_replied()
        out = self._run()
        self.assertIn("活跃", out["verdict"])

    def test_silent_with_reports(self):
        self._report()
        out = self._run()
        self.assertIn("纯沉默", out["verdict"])

    def test_broken_no_reports(self):
        out = self._run()
        self.assertIn("故障", out["verdict"])

    def test_old_signals_outside_window(self):
        self._report()
        self._evidence(days_ago=30)  # 30 天前的反馈，14 天窗口外
        out = self._run(days=14)
        self.assertEqual(out["老板反馈"], 0)
        self.assertIn("纯沉默", out["verdict"])


if __name__ == "__main__":
    unittest.main()