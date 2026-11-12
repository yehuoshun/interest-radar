"""core：路径口径回归。

原来靠「向上找 skills/interest-radar 标记」定位 `~/.openclaw/workspace/interests`，
2026-11-13 改成跨平台：状态目录默认 `<仓库根>/state`，cookie 默认 `<工作区>/config/bilibili_cookies.txt`
（工作区布局 `<workspace>/{code,work}/<项目>`，config/ 下也认历史命名 `bilibili.txt`）。
这两条口径错了，整个雷达的读写都会散到不该去的目录，所以钉死在这里。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bili_radar.core as core  # noqa: E402
from bili_radar.core import cookie_path, state_dir  # noqa: E402


class TestStateDir(unittest.TestCase):
    def test_default_is_repo_state_dir(self):
        old = os.environ.pop("INTERESTS_DIR", None)
        try:
            d = state_dir()
            self.assertEqual(d, core.REPO_ROOT / "state", f"算错了：{d}")
            self.assertEqual(d.name, "state")
        finally:
            if old is not None:
                os.environ["INTERESTS_DIR"] = old

    def test_env_override(self):
        old = os.environ.get("INTERESTS_DIR")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["INTERESTS_DIR"] = tmp
            try:
                self.assertEqual(state_dir(), Path(tmp))
            finally:
                if old is None:
                    os.environ.pop("INTERESTS_DIR", None)
                else:
                    os.environ["INTERESTS_DIR"] = old

    def test_ensure_state_dir_creates(self):
        old = os.environ.get("INTERESTS_DIR")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "deep", "state")
            os.environ["INTERESTS_DIR"] = str(target)
            try:
                self.assertEqual(core.ensure_state_dir(), target)
                self.assertTrue(target.is_dir())
            finally:
                if old is None:
                    os.environ.pop("INTERESTS_DIR", None)
                else:
                    os.environ["INTERESTS_DIR"] = old


class TestCookiePath(unittest.TestCase):
    """候选顺序：工作区 config/ → 仓库 config/ → 旧 OpenClaw secrets/（只读兼容）。"""

    def setUp(self):
        os.environ.pop("BILI_COOKIE_FILE", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / "workspace" / "code" / "interest-radar"
        self.repo.mkdir(parents=True)
        self._old = (core.REPO_ROOT, core.LEGACY_COOKIE)
        core.REPO_ROOT = self.repo
        core.LEGACY_COOKIE = self.root / "legacy" / "bilibili-cookies.txt"

    def tearDown(self):
        core.REPO_ROOT, core.LEGACY_COOKIE = self._old
        os.environ.pop("BILI_COOKIE_FILE", None)
        self._tmp.cleanup()

    def _touch(self, p: Path):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("SESSDATA=x; bili_jct=y; DedeUserID=1\n", encoding="utf-8")

    def test_env_wins(self):
        os.environ["BILI_COOKIE_FILE"] = str(self.root / "elsewhere.txt")
        self.assertEqual(cookie_path(), self.root / "elsewhere.txt")

    def test_workspace_config_first(self):
        ws_cookie = self.root / "workspace" / "config" / "bilibili_cookies.txt"
        repo_cookie = self.repo / "config" / "bilibili_cookies.txt"
        self._touch(repo_cookie)
        self._touch(ws_cookie)
        self.assertEqual(cookie_path(), ws_cookie)

    def test_repo_config_when_no_workspace_one(self):
        repo_cookie = self.repo / "config" / "bilibili_cookies.txt"
        self._touch(repo_cookie)
        self.assertEqual(cookie_path(), repo_cookie)

    def test_legacy_openclaw_still_read(self):
        legacy = Path(self.root, "legacy", "bilibili-cookies.txt")
        self._touch(legacy)
        self.assertEqual(cookie_path(), legacy)

    def test_alt_name_bilibili_txt(self):
        """历史命名 bilibili.txt 也认（本机 config/ 就是这个名）。"""
        ws_cookie = self.root / "workspace" / "config" / "bilibili.txt"
        self._touch(ws_cookie)
        self.assertEqual(cookie_path(), ws_cookie)

    def test_prefers_canonical_name_over_alt(self):
        ws = self.root / "workspace" / "config"
        self._touch(ws / "bilibili.txt")
        self._touch(ws / "bilibili_cookies.txt")
        self.assertEqual(cookie_path(), ws / "bilibili_cookies.txt")

    def test_missing_defaults_to_workspace_config(self):
        self.assertEqual(cookie_path(),
                         self.root / "workspace" / "config" / "bilibili_cookies.txt")

    def test_missing_without_code_layout_defaults_to_repo_config(self):
        bare = self.root / "checkout"
        (bare / "scripts").mkdir(parents=True)
        core.REPO_ROOT = bare
        self.assertEqual(cookie_path(), bare / "config" / "bilibili_cookies.txt")


class TestWorkspaceRoot(unittest.TestCase):
    def test_code_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "ws", "code", "proj")
            repo.mkdir(parents=True)
            old = core.REPO_ROOT
            core.REPO_ROOT = repo
            try:
                self.assertEqual(core.workspace_root(), Path(tmp, "ws"))
            finally:
                core.REPO_ROOT = old

    def test_work_layout(self):
        """工作任务放 work/ 下，同样算分组目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "ws", "work", "proj")
            repo.mkdir(parents=True)
            old = core.REPO_ROOT
            core.REPO_ROOT = repo
            try:
                self.assertEqual(core.workspace_root(), Path(tmp, "ws"))
            finally:
                core.REPO_ROOT = old

    def test_bare_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "proj")
            repo.mkdir()
            old = core.REPO_ROOT
            core.REPO_ROOT = repo
            try:
                self.assertEqual(core.workspace_root(), repo)
            finally:
                core.REPO_ROOT = old


if __name__ == "__main__":
    unittest.main()
