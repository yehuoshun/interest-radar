"""B1（2026-11-02）审批闸：敏感项直改需老板批准，propose → approve/reject 闭环。

覆盖：
- set --yes 敏感项无批准 → 拒绝（exit 1）
- set --yes 敏感项带 --approved-by → 放行 + 账本留痕
- set 非敏感项直改不需要批准
- propose 提交 / 同参数重复 pending 拒绝 / 不碰 config
- approve → 真写 + 账本 actor=boss + proposals 状态流转；重复 approve 拒绝
- reject → 不写 + 状态流转
- proposals 列表 / --all / --json / stale 标记
- approve 时路径已死 → 拒绝执行
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
    "mention": {"enabled": True, "name": "夜灬瞬", "mid": 239028467, "forbid": [],
                "per_round": 1, "per_hour": 1, "per_day": 0},
    "write": {"cooldown_sec": 120,
              "message": {"enabled": True, "per_hour": 0, "per_day": 5,
                          "allow_mid": [239028467]}},
    "draft": {"enabled": True, "per_12h": 1, "per_24h": 2},
}


def setup(tmp: Path):
    Path(tmp, "config.json").write_text(
        json.dumps(CONFIG, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_cfg(tmp):
    return json.loads(Path(tmp, "config.json").read_text(encoding="utf-8"))


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


def set_yes(tmp, path, value, **kw):
    base = dict(path=path, value=value, yes=True, reason=None,
                actor="agent", approved_by=None)
    base.update(kw)
    return run(R.cmd_cfg_set, Namespace(**base))


def load_proposals(tmp):
    f = Path(tmp, "proposals.json")
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


class TestSensitiveGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_sensitive_set_without_approval_dies(self):
        code, out, err = set_yes(self.tmp, "mention.per_hour", "2")
        self.assertEqual(code, 1)
        self.assertIn("敏感项", err)
        self.assertIn("--approved-by", err)
        self.assertIn("propose", err)
        # 没写入、没备份、没账本
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_hour"], 1)
        self.assertEqual(list(self.tmp.glob("config.json.bak-*")), [])
        self.assertFalse(Path(self.tmp, "param-history.jsonl").exists())

    def test_sensitive_set_with_approval_writes_and_records(self):
        code, out, _ = set_yes(self.tmp, "mention.per_hour", "2",
                               approved_by="老板微信：一小时一条太多改两条")
        self.assertEqual(code, 0)
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_hour"], 2)
        rows = [json.loads(l) for l in Path(self.tmp, "param-history.jsonl")
                .read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(rows[0]["kind"], "change")
        self.assertEqual(rows[0]["approved_by"], "老板微信：一小时一条太多改两条")

    def test_nonsensitive_set_no_approval_needed(self):
        # mention.name 不在敏感清单 → 直改无需批准
        code, _, err = set_yes(self.tmp, "mention.name", "夜灬瞬二号")
        self.assertEqual(code, 0, err)
        self.assertEqual(read_cfg(self.tmp)["mention"]["name"], "夜灬瞬二号")

    def test_dry_run_nonsensitive_unaffected(self):
        # 干跑（无 --yes）敏感项也不拦（只看 diff）
        code, out, _ = run(R.cmd_cfg_set, Namespace(path="mention.per_hour",
                                                    value="2", yes=False,
                                                    reason=None, actor="agent",
                                                    approved_by=None))
        self.assertEqual(code, 0)
        self.assertIn("干跑", out)
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_hour"], 1)

    def test_dry_run_normal_key_missing_dies(self):
        code, _, err = set_yes(self.tmp, "nope.key", "1")
        self.assertEqual(code, 1)
        self.assertIn("停在 nope", err)


class TestProposeFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_propose_creates_pending_without_touching_config(self):
        code, out, _ = run(R.cmd_cfg_propose,
                           Namespace(path="mention.per_hour", value="2",
                                      reason="想试试两小时一条"))
        self.assertEqual(code, 0)
        items = load_proposals(self.tmp)
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["path"], "mention.per_hour")
        self.assertEqual(it["value"], 2)
        self.assertEqual(it["status"], "pending")
        self.assertIn("pln-", it["id"])
        self.assertIn(it["id"], out)
        # config 完全没动
        self.assertEqual(read_cfg(self.tmp), CONFIG)

    def test_duplicate_pending_same_param_dies(self):
        run(R.cmd_cfg_propose, Namespace(path="mention.per_hour", value="2",
                                          reason=None))
        code, _, err = run(R.cmd_cfg_propose,
                           Namespace(path="mention.per_hour", value="3",
                                      reason=None))
        self.assertEqual(code, 1)
        self.assertIn("已有待批申请", err)

    def test_propose_unknown_path_dies(self):
        code, _, err = run(R.cmd_cfg_propose,
                           Namespace(path="nope.key", value="1", reason=None))
        self.assertEqual(code, 1)
        self.assertIn("停在 nope", err)

    def test_approve_writes_as_boss_and_marks_approved(self):
        run(R.cmd_cfg_propose, Namespace(path="mention.per_hour", value="2",
                                          reason=None))
        pid = load_proposals(self.tmp)[0]["id"]
        code, out, _ = run(R.cmd_cfg_approve, Namespace(id=pid))
        self.assertEqual(code, 0)
        # 写入生效
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_hour"], 2)
        # 状态流转 + 账本 actor=boss + 批准留痕
        items = load_proposals(self.tmp)
        self.assertEqual(items[0]["status"], "approved")
        rows = [json.loads(l) for l in Path(self.tmp, "param-history.jsonl")
                .read_text(encoding="utf-8").splitlines() if l.strip()]
        chg = rows[0]
        self.assertEqual(chg["actor"], "boss")
        self.assertEqual(chg["approved_by"], f"config approve {pid}")
        self.assertIn("已批准", out)

    def test_approve_twice_dies(self):
        run(R.cmd_cfg_propose, Namespace(path="mention.per_hour", value="2",
                                          reason=None))
        pid = load_proposals(self.tmp)[0]["id"]
        run(R.cmd_cfg_approve, Namespace(id=pid))
        code, _, err = run(R.cmd_cfg_approve, Namespace(id=pid))
        self.assertEqual(code, 1)
        self.assertIn("不能重复处理", err)

    def test_approve_unknown_id_dies(self):
        code, _, err = run(R.cmd_cfg_approve, Namespace(id="pln-nope"))
        self.assertEqual(code, 1)
        self.assertIn("没有这个申请", err)

    def test_reject_does_not_write(self):
        run(R.cmd_cfg_propose, Namespace(path="mention.per_hour", value="2",
                                          reason=None))
        pid = load_proposals(self.tmp)[0]["id"]
        code, out, _ = run(R.cmd_cfg_reject, Namespace(id=pid, reason="暂不想动"))
        self.assertEqual(code, 0)
        self.assertIn("已驳回", out)
        self.assertEqual(read_cfg(self.tmp), CONFIG)  # 一笔没动
        items = load_proposals(self.tmp)
        self.assertEqual(items[0]["status"], "rejected")
        self.assertEqual(items[0]["decided_note"], "暂不想动")
        # rejected 后可重新 propose
        code2, _, _ = run(R.cmd_cfg_propose, Namespace(path="mention.per_hour",
                                                       value="3", reason=None))
        self.assertEqual(code2, 0)

    def test_proposals_list_and_json(self):
        run(R.cmd_cfg_propose, Namespace(path="mention.per_hour", value="2",
                                          reason="测试"))
        pid = load_proposals(self.tmp)[0]["id"]
        code, out, _ = run(R.cmd_cfg_proposals, Namespace(all=False, json=False))
        self.assertEqual(code, 0)
        self.assertIn("⏳", out)
        self.assertIn("mention.per_hour", out)
        self.assertIn("理由：测试", out)
        # 处理后默认列表为空 → 提示 --all
        run(R.cmd_cfg_approve, Namespace(id=pid))
        code2, out2, _ = run(R.cmd_cfg_proposals, Namespace(all=False, json=False))
        self.assertIn("没有待批申请", out2)
        code3, out3, _ = run(R.cmd_cfg_proposals, Namespace(all=True, json=False))
        self.assertIn("✅", out3)
        # json
        code4, out4, _ = run(R.cmd_cfg_proposals, Namespace(all=True, json=True))
        data = json.loads(out4)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["items"][0]["status"], "approved")

    def test_stale_marker_after_24h(self):
        run(R.cmd_cfg_propose, Namespace(path="mention.per_hour", value="2",
                                          reason=None))
        items = load_proposals(self.tmp)
        items[0]["ts"] = "2026-10-31T09:00:00"  # 人为推到过去
        Path(self.tmp, "proposals.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        code, out, _ = run(R.cmd_cfg_proposals, Namespace(all=False, json=False))
        self.assertEqual(code, 0)
        self.assertIn("stale", out)


if __name__ == "__main__":
    unittest.main()