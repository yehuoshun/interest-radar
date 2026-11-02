"""verify-params：参数采用对账（A2）—— 保存值 vs 运行证据的判定逻辑。

覆盖：空状态全 pending / @ 频控 adopted+conflict / 写冷却 conflict /
write 分 kind 频控 / 日报最低分越阈值 conflict / --json 输出 / 静态表（死配置+漂移）。
零网络、零写入（全在 INTERESTS_DIR 指向的临时目录）。
"""
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timedelta
from io import StringIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bili_radar import cli as R

NOW = datetime.now()


def iso(ago_min: float) -> str:
    return (NOW - timedelta(minutes=ago_min)).isoformat(timespec="seconds")


def write_cfg(tmp: Path, **over):
    cfg = {
        "mention": {"per_round": 1, "per_hour": 1, "per_day": 0, "min_score": 17,
                    "template": "@{name} {why}"},
        "budget": {"max_subtitles_per_round": 0, "max_push_per_round": 1,
                   "min_total_score": 14},
        "write": {"cooldown_sec": 120,
                  "dynamic": {"enabled": True, "per_hour": 0, "per_day": 3},
                  "message": {"enabled": True, "per_hour": 0, "per_day": 5},
                  "comment": {"enabled": True, "per_hour": 3, "per_day": 0}},
        "draft": {"enabled": True, "per_12h": 1, "per_24h": 2},
    }
    for k, v in over.items():
        cfg[k] = v
    Path(tmp, "config.json").write_text(json.dumps(cfg, ensure_ascii=False),
                                        encoding="utf-8")


def add_log(tmp: Path, fname: str, rows):
    rows = [r if isinstance(r, dict) else {"ts": r, "kind": "comment"} for r in rows]
    with Path(tmp, fname).open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def run(tmp: Path, json_out=False):
    out, err = StringIO(), StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    code = 0
    try:
        R.cmd_verify_params(Namespace(json=json_out))
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.stdout, sys.stderr = old
    return code, out.getvalue(), err.getvalue()


class TestVerifyParams(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    # ── 空状态：全部无证据 → pending，无 conflict ──────────────────
    def test_empty_state_all_pending(self):
        write_cfg(self.tmp)
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 0)
        self.assertIn("账本空", out)
        self.assertIn("无写记录", out)
        self.assertIn("今天还没有日报", out)
        self.assertIn("无已批草稿", out)
        self.assertIn("推送证据在微信侧", out)
        self.assertIn("❌ conflict 0", out)

    # ── @ 频控 ─────────────────────────────────────────────────────
    def test_mentions_adopted_within_limit(self):
        write_cfg(self.tmp)
        add_log(self.tmp, "mention-log.jsonl",
                [{"ts": iso(10), "bv": "BV1", "kind": "mentioned"}])
        _, out, _ = run(self.tmp)
        self.assertIn("✅[adopted] mention.per_hour", out)
        self.assertIn("❌ conflict 0", out)

    def test_mentions_conflict_over_limit(self):
        write_cfg(self.tmp)
        add_log(self.tmp, "mention-log.jsonl",
                [{"ts": iso(44), "bv": "BV1", "kind": "mentioned"},
                 {"ts": iso(22), "bv": "BV2", "kind": "mentioned"}])
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 3)  # conflict → exit 3（cron 告警位）
        self.assertIn("❌[conflict] mention.per_hour", out)

    # ── 写冷却 ─────────────────────────────────────────────────────
    def test_cooldown_boundary_ok(self):
        write_cfg(self.tmp)
        add_log(self.tmp, "write-log.jsonl", [iso(5), iso(3)])  # 间隔恰好 120s = 上限，不超
        code, out, _ = run(self.tmp)
        self.assertIn("✅[adopted] write.cooldown_sec", out)
        self.assertEqual(code, 0)

    def test_cooldown_conflict_under_120s(self):
        write_cfg(self.tmp)
        add_log(self.tmp, "write-log.jsonl",
                [(NOW - timedelta(seconds=60)).isoformat(timespec="seconds"),
                 (NOW - timedelta(seconds=30)).isoformat(timespec="seconds")])
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 3)
        self.assertIn("相邻写间隔", out)

    def test_cooldown_mixed_naive_aware_no_crash(self):
        """真实账本存在人工补录的 +08:00 行（10-27 老板确认记录）——naive/aware 混排不能崩。"""
        write_cfg(self.tmp)
        add_log(self.tmp, "write-log.jsonl", [iso(30)])
        add_log(self.tmp, "mention-log.jsonl",
                [{"ts": "2026-10-27T15:05:00+08:00", "bv": "BV1", "kind": "confirmed-by-boss"}])
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", out)

    def test_cooldown_old_history_gap_ignored(self):
        """写冷却 10-27 才引入：7 天前的密集 @ 是旧行为，被 cutoff 排除 → pending 而非 conflict。"""
        write_cfg(self.tmp)
        add_log(self.tmp, "mention-log.jsonl",
                [{"ts": "2026-10-16T20:01:15", "bv": "BV1", "kind": "mentioned"},
                 {"ts": "2026-10-16T20:01:19", "bv": "BV2", "kind": "mentioned"}])
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 0)
        self.assertIn("⏳[pending] write.cooldown_sec", out)

    def test_cooldown_recent_gap_still_conflict(self):
        """7 天窗口内的 4s gap 必须还是 conflict（边界内计数）。"""
        write_cfg(self.tmp)
        add_log(self.tmp, "mention-log.jsonl",
                [{"ts": (NOW - timedelta(days=3, seconds=50)).isoformat(timespec="seconds"),
                  "bv": "BV1", "kind": "mentioned"},
                 {"ts": (NOW - timedelta(days=3, seconds=46)).isoformat(timespec="seconds"),
                  "bv": "BV2", "kind": "mentioned"}])
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 3)
        self.assertIn("相邻写间隔", out)

    # ── write 分 kind 频控 ─────────────────────────────────────────
    def test_write_kind_day_limit_conflict(self):
        write_cfg(self.tmp)
        add_log(self.tmp, "write-log.jsonl",
                [{"ts": iso(22 * i + 1), "kind": "dynamic"} for i in range(4)])  # 4 条/24h > 3
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 3)
        self.assertIn("❌[conflict] write.dynamic.per_day", out)

    def test_write_kind_absent_is_pending(self):
        write_cfg(self.tmp)
        add_log(self.tmp, "write-log.jsonl", [{"ts": iso(30), "kind": "comment"}])
        _, out, _ = run(self.tmp)
        self.assertIn("write.dynamic 频控", out)
        self.assertIn("pending", out)

    # ── 日报最低分 vs min_total_score ─────────────────────────────
    def test_report_scores_below_threshold_conflict(self):
        write_cfg(self.tmp)
        (self.tmp / "out").mkdir()
        Path(self.tmp, "out", f"{NOW:%Y-%m-%d}.md").write_text(
            "# 兴趣雷达\n\n- BV1（5/4/4/5）= 18\n- BV2（3/3/3/3）= 12\n",
            encoding="utf-8")
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 3)
        self.assertIn("最低分 12", out)

    def test_report_scores_ok_adopted(self):
        write_cfg(self.tmp)
        (self.tmp / "out").mkdir()
        Path(self.tmp, "out", f"{NOW:%Y-%m-%d}.md").write_text(
            "# 兴趣雷达\n\n- BV1（5/4/4/5）= 18\n",
            encoding="utf-8")
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 0)
        self.assertIn("✅[adopted] budget.min_total_score", out)

    # ── --json 输出 ────────────────────────────────────────────────
    def test_json_output_parses(self):
        write_cfg(self.tmp)
        code, out, _ = run(self.tmp, json_out=True)
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertIn("summary", data)
        self.assertIn("rows", data)
        self.assertEqual(data["conflict_exit"], 0)

    # ── 静态表：死配置 + 漂移 ─────────────────────────────────────
    def test_not_consumed_and_drift_listed(self):
        write_cfg(self.tmp)
        _, out, _ = run(self.tmp)
        for marker in ("mention.per_round", "mention.min_score",
                       "mention.template", "budget.max_subtitles_per_round"):
            self.assertIn("not-consumed", out)
            self.assertIn(marker, out)
        self.assertIn("drift:", out)
        self.assertIn("charter.md:39", out)  # 问题 1 的口径互斥
        self.assertIn("budget.max_push_per_round", out)  # 问题 2

    # ── 配置段缺失要健壮（空 config.json）────────────────────────
    def test_missing_cfg_sections_no_crash(self):
        Path(self.tmp, "config.json").write_text("{}", encoding="utf-8")
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()