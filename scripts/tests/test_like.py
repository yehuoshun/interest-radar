"""点赞闸（2026-11-13）：`like --bv` 的开关/频控/同一视频只点一次，零网络。

只看闸门本身（真发那条路径要真 cookie，这里不碰）：开关没开 die(4)、
赞过的再赞 die(13)、干跑正常打印、取消赞不受「同一视频一次」限制。
"""
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bili_radar import cli as R


def write_cfg(tmp, like=None):
    cfg = {"write": {"cooldown_sec": 0,
                     "like": like if like is not None else
                     {"enabled": True, "per_hour": 0, "per_day": 0,
                      "same_video_once": True, "forbid": []}}}
    Path(tmp, "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")


def dry_like(tmp, **kw):
    """跑 cmd_like：返回 (code, out, err)。"""
    os.environ["BILI_COOKIE_FILE"] = str(tmp / "cookie")
    Path(tmp, "cookie").write_text("SESSDATA=abc; bili_jct=xyz", encoding="utf-8")
    args = dict(bv="BV1", cancel=False, yes=False)
    args.update(kw)
    out, err = StringIO(), StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    code = 0
    try:
        with mock.patch("bili_radar.like.get",
                        return_value={"code": 0, "data": {"aid": 42, "title": "T"}}):
            R.cmd_like(Namespace(**args))
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.stdout, sys.stderr = old
        os.environ.pop("BILI_COOKIE_FILE", None)
    return code, out.getvalue(), err.getvalue()


class TestLikeGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        write_cfg(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_disabled_switch_dies_4(self):
        write_cfg(self.tmp, {"enabled": False})
        code, _, err = dry_like(self.tmp)
        self.assertEqual(code, 4)
        self.assertIn("write.like.enabled", err)

    def test_dry_run_prints_plan_and_does_not_write_log(self):
        code, out, err = dry_like(self.tmp)
        self.assertEqual(code, 0)
        self.assertIn('"dry_run": true', out)
        self.assertIn("加 --yes", err)
        self.assertFalse(Path(self.tmp, "write-log.jsonl").exists())

    def test_same_video_once_dies_13(self):
        Path(self.tmp, "write-log.jsonl").write_text(
            json.dumps({"ts": "2026-11-13T00:00:00", "kind": "like", "bv": "BV1"}) + "\n",
            encoding="utf-8")
        code, _, err = dry_like(self.tmp)
        self.assertEqual(code, 13)
        self.assertIn("只点一次", err)

    def test_cancel_bypasses_same_video_gate(self):
        Path(self.tmp, "write-log.jsonl").write_text(
            json.dumps({"ts": "2026-11-13T00:00:00", "kind": "like", "bv": "BV1"}) + "\n",
            encoding="utf-8")
        code, out, _ = dry_like(self.tmp, cancel=True)
        self.assertEqual(code, 0)
        self.assertIn('"like": 0', out)


if __name__ == "__main__":
    unittest.main()
