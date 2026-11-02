"""B2（2026-11-02）预算硬闸：comment --score —— 低于 budget.min_total_score 被 code 拒发。

分数只存在于模型推理/日报，代码层无从自取 → 闸设计为「可选-必校验」：
- 传了 --score → 低于阈值 die(14)（真硬闸，不达标拒绝）
- 不传 → 不拦，但 stderr 提示（诚实地软）
测试只用 前置闸位（_write_gate 之后、text 校验附近），零网络。
"""
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bili_radar import cli as R


def cfg_with_comment(tmp):
    Path(tmp, "config.json").write_text(json.dumps({
        "budget": {"min_total_score": 14},
        "write": {"comment": {"enabled": True, "per_hour": 0, "per_day": 0,
                               "forbid": []}},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dry_comment(tmp, **kw):
    """跑 cmd_comment：返回 (code, out, err)。干跑打印在 fetch video 之后 → mock 网络。"""
    from io import StringIO
    from unittest import mock
    os.environ["BILI_COOKIE_FILE"] = str(tmp / "cookie")
    Path(tmp, "cookie").write_text("SESSDATA=abc; bili_jct=xyz", encoding="utf-8")
    args = dict(bv="BV1", text="测试正文", score=None, yes=False, reply_to=None)
    args.update(kw)
    out, err = StringIO(), StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    code = 0
    try:
        with mock.patch("bili_radar.comment.get",
                         return_value={"code": 0, "data": {"aid": 42, "title": "T"}}):
            R.cmd_comment(Namespace(**args))
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.stdout, sys.stderr = old
        os.environ.pop("BILI_COOKIE_FILE", None)
    return code, out.getvalue(), err.getvalue()


class TestCommentScoreGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        cfg_with_comment(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_score_below_floor_dies_14(self):
        code, _, err = dry_comment(self.tmp, score=5)
        self.assertEqual(code, 14)
        self.assertIn("B2", err)
        self.assertIn("5 < 下限 14", err)

    def test_score_at_floor_passes_gate(self):
        # 14 == 下限 → 过闸；换成空正文 → 应倒在闸③（正文为空 7），而不是分数闸
        code, _, err = dry_comment(self.tmp, score=14, text="")
        self.assertEqual(code, 7)  # 闸③ 正文为空（说明分数闸已放行）

    def test_score_above_floor_passes_gate(self):
        code, _, _ = dry_comment(self.tmp, score=18)
        self.assertEqual(code, 0)  # 干跑正常打印（不触发分数闸）

    def test_no_score_prints_hint_but_not_block(self):
        code, _, err = dry_comment(self.tmp, score=None)
        self.assertEqual(code, 0)
        self.assertIn("没带 --score", err)

    def test_floor_reads_from_config(self):
        # 阈值来自 config：把 budget.min_total_score 抬到 20 → 18 就不行了
        cfg = json.loads(Path(self.tmp, "config.json").read_text(encoding="utf-8"))
        cfg["budget"]["min_total_score"] = 20
        Path(self.tmp, "config.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        code, _, err = dry_comment(self.tmp, score=18)
        self.assertEqual(code, 14)
        self.assertIn("18 < 下限 20", err)


if __name__ == "__main__":
    unittest.main()