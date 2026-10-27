"""core：state_dir 路径回归（包化后不能算成 skills/interests —— 2026-10-27 踩过）。"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bili_radar.core import state_dir


class TestStateDir(unittest.TestCase):
    """两种布局都要算对：

    ① skill 安装布局  <workspace>/skills/interest-radar/scripts/tests/
    ② 裸 checkout    <repo>/scripts/tests/（CI 就是这种，没有 skills/ 层）
    """

    def test_default_points_to_workspace_interests(self):
        old = os.environ.pop("INTERESTS_DIR", None)
        try:
            d = state_dir()
            here = Path(__file__).resolve()

            # 已知 bug 的产物是 .../skills/interests —— 两种布局都不许出现
            self.assertEqual(d.name, "interests", f"算错了：{d}")
            self.assertNotEqual(d.parent.name, "skills", f"退化成 skills/interests 了：{d}")

            marker = next((p for p in here.parents if (p / "skills" / "interest-radar").is_dir()), None)
            if marker is not None:
                # ① 有技能安装标记 → 落在标记的上一级
                self.assertEqual(d, marker / "interests")
            else:
                # ② 裸 checkout → 落在仓库根（tests → scripts → 仓库根）
                repo_root = here.parents[2]
                self.assertEqual(d, repo_root / "interests")
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