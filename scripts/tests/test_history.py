"""参数变更账本（A4）：change/rollback/observe 三条事件 + log/observe 命令 + diff。

零网络、零真实写入（全在 INTERESTS_DIR 指向的临时目录）。
"""
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bili_radar import cli as R

CONFIG = {
    "mention": {"per_round": 1, "per_hour": 1, "per_day": 0},
    "budget": {"max_push_per_round": 1, "min_total_score": 14},
    "write": {"cooldown_sec": 120,
              "dynamic": {"enabled": True, "per_day": 3}},
}


def setup(tmp: Path):
    Path(tmp, "config.json").write_text(json.dumps(CONFIG, ensure_ascii=False, indent=2)
                                        + "\n", encoding="utf-8")


def read_hist(tmp):
    f = Path(tmp, "param-history.jsonl")
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def run(fn, ns):
    out, err = StringIO(), StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    code = 0
    try:
        fn(ns)
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.stdout, sys.stderr = old
    return code, out.getvalue(), err.getvalue()


class TestHistoryAppend(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_append_change_fields(self):
        cid = R.append_change(self.tmp, actor="boss", param="mention.per_hour",
                               before=1, after=2, reason="一小时一条太多")
        rows = read_hist(self.tmp)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["kind"], "change")
        self.assertEqual(r["id"], cid)
        self.assertEqual(r["actor"], "boss")
        self.assertEqual(r["param"], "mention.per_hour")
        self.assertEqual(r["before"], 1)
        self.assertEqual(r["after"], 2)
        self.assertEqual(r["reason"], "一小时一条太多")

    def test_append_observe_and_rollback(self):
        cid = R.append_change(self.tmp, actor="agent", param="mention.per_day",
                               before=0, after=2)
        oid = R.append_observe(self.tmp, change_id=cid, note="一周后老板没抱怨，保留")
        R.append_rollback(self.tmp, backup_name="config.json.bak-20261102-100000-abc",
                          changed=[["mention.per_day", 2, 0]])
        rows = read_hist(self.tmp)
        self.assertEqual(len(rows), 3)
        by_kind = {r["kind"]: r for r in rows}
        self.assertEqual(by_kind["observe"]["change_id"], cid)
        self.assertEqual(by_kind["observe"]["id"], oid)
        self.assertEqual(by_kind["rollback"]["rollback_to"],
                         "config.json.bak-20261102-100000-abc")
        self.assertEqual(by_kind["rollback"]["changed"][0],
                         ["mention.per_day", 2, 0])


class TestDiffParams(unittest.TestCase):
    def test_flat_and_nested(self):
        old = {"budget": {"min_total_score": 14, "x": 1},
               "write": {"dynamic": {"per_day": 3}, "enabled": True}}
        new = {"budget": {"min_total_score": 15, "x": 1},
               "write": {"dynamic": {"per_day": 5}, "enabled": True}}
        out = R.diff_params(old, new)
        self.assertIn(["budget.min_total_score", 14, 15], out)
        self.assertIn(["write.dynamic.per_day", 3, 5], out)
        self.assertEqual(len(out), 2)

    def test_added_and_removed_keys(self):
        out = R.diff_params({"a": 1}, {"a": 1, "b": 2})
        self.assertIn(["b", "<absent>", 2], out)
        out2 = R.diff_params({"a": 1, "b": 2}, {"a": 1})
        self.assertIn(["b", 2, "<absent>"], out2)


class TestCmdLog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_log_empty(self):
        code, out, _ = run(R.cmd_cfg_log, Namespace(param=None, json=False))
        self.assertEqual(code, 0)
        self.assertIn("账本为空", out)

    def test_log_with_history_and_filter(self):
        c1 = R.append_change(self.tmp, actor="boss", param="mention.per_hour",
                              before=1, after=2, reason="调整")
        R.append_change(self.tmp, actor="agent", param="budget.min_total_score",
                         before=14, after=15)
        R.append_observe(self.tmp, change_id=c1, note="效果不错")
        code, out, _ = run(R.cmd_cfg_log, Namespace(param=None, json=False))
        self.assertEqual(code, 0)
        self.assertIn("CHG", out)
        self.assertIn("mention.per_hour", out)
        self.assertIn("理由：调整", out)
        self.assertIn("观察", out)
        # --param 过滤后只剩相关行
        code2, out2, _ = run(R.cmd_cfg_log, Namespace(param="mention.per_hour",
                                                      json=False))
        self.assertIn("mention.per_hour", out2)
        self.assertNotIn("budget.min_total_score", out2)
        # observe 跟随其 change 出现（change_id 关联）
        self.assertIn("效果不错", out2)

    def test_log_json(self):
        R.append_change(self.tmp, actor="agent", param="mention.per_hour",
                        before=1, after=2)
        code, out, _ = run(R.cmd_cfg_log, Namespace(param=None, json=True))
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["rows"][0]["param"], "mention.per_hour")


class TestCmdObserve(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_observe_ok(self):
        cid = R.append_change(self.tmp, actor="boss", param="mention.per_hour",
                               before=1, after=2)
        code, out, _ = run(R.cmd_cfg_observe,
                           Namespace(change_id=cid, note="跑了一周挺稳"))
        self.assertEqual(code, 0)
        rows = read_hist(self.tmp)
        self.assertEqual(rows[-1]["kind"], "observe")
        self.assertEqual(rows[-1]["change_id"], cid)

    def test_observe_unknown_change_dies(self):
        code, _, err = run(R.cmd_cfg_observe,
                           Namespace(change_id="chg-nope", note="x"))
        self.assertEqual(code, 1)
        self.assertIn("找不到变更", err)


class TestWiring(unittest.TestCase):
    """set / rate / restore 真写路径要自动入账本（A4 写入点）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_set_yes_writes_history_dry_run_not(self):
        # 干跑：不写账本
        run(R.cmd_cfg_set, Namespace(path="mention.per_hour", value="2",
                                     yes=False, reason="测试", actor="agent"))
        self.assertEqual(read_hist(self.tmp), [])
        # 真写：入账本
        code, out, _ = run(R.cmd_cfg_set, Namespace(path="mention.per_hour",
                                                    value="2", yes=True,
                                                    reason="一小时一条太多",
                                                    actor="boss"))
        self.assertEqual(code, 0)
        rows = read_hist(self.tmp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["actor"], "boss")
        self.assertEqual(rows[0]["reason"], "一小时一条太多")
        self.assertIn("账本：chg-", out)

    def test_rate_writes_history(self):
        run(R.cmd_rate, Namespace(per_round=2, per_hour=None, per_day=None))
        rows = read_hist(self.tmp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["param"], "mention.per_round")
        self.assertEqual(rows[0]["before"], 1)
        self.assertEqual(rows[0]["after"], 2)

    def test_restore_writes_rollback_row(self):
        run(R.cmd_cfg_set, Namespace(path="mention.per_hour", value="2",
                                     yes=True, reason=None, actor="agent"))
        bak = sorted(p.name for p in self.tmp.glob("config.json.bak-*"))[0]
        run(R.cmd_cfg_restore, Namespace(name=bak, list=False, yes=True))
        rows = read_hist(self.tmp)
        self.assertEqual(rows[-1]["kind"], "rollback")
        self.assertEqual(rows[-1]["rollback_to"], bak)
        self.assertIn(["mention.per_hour", 2, 1], rows[-1]["changed"])

    def test_restore_dry_run_no_history(self):
        run(R.cmd_cfg_set, Namespace(path="mention.per_hour", value="2",
                                     yes=True, reason=None, actor="agent"))
        bak = sorted(p.name for p in self.tmp.glob("config.json.bak-*"))[0]
        run(R.cmd_cfg_restore, Namespace(name=bak, list=False, yes=False))
        kinds = [r["kind"] for r in read_hist(self.tmp)]
        self.assertEqual(kinds, ["change"])  # 只有 set 的行，restore 干跑没写


if __name__ == "__main__":
    unittest.main()