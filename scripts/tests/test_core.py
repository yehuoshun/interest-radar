"""core：state_dir 路径回归（包化后不能算成 skills/interests —— 2026-10-27 踩过）。"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from radar_lib.core import state_dir


class TestStateDir(unittest.TestCase):
    def test_default_points_to_workspace_interests(self):
        old = os.environ.pop("INTERESTS_DIR", None)
        try:
            # 本文件在 <workspace>/skills/interest-radar/scripts/tests/
            expected = Path(__file__).resolve().parents[4] / "interests"
            self.assertEqual(state_dir(), expected)
            self.assertTrue(str(state_dir()).endswith("/workspace/interests"),
                            f"算错了：{state_dir()}")
        finally:
            if old is not None:
                os.environ["INTERESTS_DIR"] = old

    def test_env_override(self):
        old = os.environ.get("INTERESTS_DIR")
        os.environ["INTERESTS_DIR"] = "/tmp/xyz"
        try:
            self.assertEqual(str(state_dir()), "/tmp/xyz")
        finally:
            if old is None:
                os.environ.pop("INTERESTS_DIR", None)
            else:
                os.environ["INTERESTS_DIR"] = old


if __name__ == "__main__":
    unittest.main()