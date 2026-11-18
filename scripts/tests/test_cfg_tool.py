"""config 工具（A3）：干跑 / 备份 / 回滚 / 敏感项与死配置提示 / rate 联动备份。

零网络、零真实写入（全在 INTERESTS_DIR 指向的临时目录；备份也落在 tmp）。
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
    "mention": {"enabled": True, "name": "夜灬瞬", "mid": 239028467,
                "per_round": 1, "per_hour": 1, "per_day": 0,
                "min_score": 17, "template": "@{name} {why}", "forbid": []},
    "budget": {"max_subtitles_per_round": 0, "max_push_per_round": 1,
               "min_total_score": 14},
    "write": {"cooldown_sec": 120,
              "message": {"enabled": True, "per_day": 5, "allow_mid": [239028467]}},
}


def setup(tmp: Path):
    Path(tmp, "config.json").write_text(json.dumps(CONFIG, ensure_ascii=False, indent=2)
                                        + "\n", encoding="utf-8")


def run_set(tmp, path, value, yes=False, **kw):
    out, err = StringIO(), StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    code = 0
    try:
        R.cmd_cfg_set(Namespace(path=path, value=value, yes=yes,
                                approved_by=kw.pop("approved_by", "测试：老板口头批准"),
                                reason=kw.pop("reason", None), actor=kw.pop("actor", "agent"),
                                **kw))
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.stdout, sys.stderr = old
    return code, out.getvalue(), err.getvalue()


def run_restore(tmp, name=None, list_=False, yes=False):
    out, err = StringIO(), StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    code = 0
    try:
        R.cmd_cfg_restore(Namespace(name=name, list=list_, yes=yes))
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.stdout, sys.stderr = old
    return code, out.getvalue(), err.getvalue()


def read_cfg(tmp):
    return json.loads(Path(tmp, "config.json").read_text(encoding="utf-8"))


class TestCfgSet(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_dry_run_does_not_write(self):
        before = Path(self.tmp, "config.json").read_bytes()
        code, out, _ = run_set(self.tmp, "mention.per_hour", "2")
        self.assertEqual(code, 0)
        self.assertIn("干跑", out)
        self.assertIn("1 → 2", out)
        self.assertEqual(Path(self.tmp, "config.json").read_bytes(), before)
        self.assertEqual(list(self.tmp.glob("config.json.bak-*")), [])

    def test_yes_writes_and_backs_up(self):
        code, out, _ = run_set(self.tmp, "mention.per_hour", "2", yes=True)
        self.assertEqual(code, 0)
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_hour"], 2)
        baks = list(self.tmp.glob("config.json.bak-*"))
        self.assertEqual(len(baks), 1)
        self.assertEqual(json.loads(baks[0].read_text(encoding="utf-8"))
                          ["mention"]["per_hour"], 1)  # 备份里是旧值

    def test_bad_path_dies_without_write(self):
        before = Path(self.tmp, "config.json").read_bytes()
        code, out, err = run_set(self.tmp, "mention.typo_key", "1")
        self.assertEqual(code, 1)
        self.assertIn("没有 mention.typo_key", err)
        self.assertEqual(Path(self.tmp, "config.json").read_bytes(), before)

    def test_top_level_missing_dies(self):
        code, _, err = run_set(self.tmp, "nope.key", "1")
        self.assertEqual(code, 1)
        self.assertIn("停在 nope", err)

    def test_json_value_list(self):
        run_set(self.tmp, "write.message.allow_mid", "[111, 222]", yes=True)
        self.assertEqual(read_cfg(self.tmp)["write"]["message"]["allow_mid"], [111, 222])

    def test_string_value_kept_as_str(self):
        run_set(self.tmp, "mention.name", "新名字", yes=True)
        self.assertEqual(read_cfg(self.tmp)["mention"]["name"], "新名字")

    def test_sensitive_hint(self):
        _, out, _ = run_set(self.tmp, "mention.enabled", "false")
        self.assertIn("🔒", out)

    def test_dead_config_and_drift_hints(self):
        _, out, _ = run_set(self.tmp, "mention.template", "x")
        self.assertIn("💤 死配置", out)
        _, out2, _ = run_set(self.tmp, "budget.max_push_per_round", "2")
        self.assertIn("漂移", out2)

    def test_same_value_noop(self):
        code, out, _ = run_set(self.tmp, "mention.per_hour", "1")
        self.assertEqual(code, 0)
        self.assertIn("无需修改", out)


class TestCfgRestore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_list_shows_backups(self):
        code, out, _ = run_set(self.tmp, "mention.per_hour", "2", yes=True)
        self.assertEqual(code, 0)
        _, out2, _ = run_restore(self.tmp, list_=True)
        self.assertIn("config.json.bak-", out2)
        self.assertIn("1 份备份", out2)

    def test_restore_roundtrip(self):
        run_set(self.tmp, "mention.per_hour", "2", yes=True)
        baks = sorted(p.name for p in self.tmp.glob("config.json.bak-*"))
        code, out, _ = run_restore(self.tmp, name=baks[0], yes=True)
        self.assertEqual(code, 0)
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_hour"], 1)  # 回到旧值
        # 恢复前又备份了一份当前（反悔可回）
        self.assertEqual(len(list(self.tmp.glob("config.json.bak-*"))), 2)

    def test_restore_dry_run_no_write(self):
        code, out, _ = run_set(self.tmp, "mention.per_hour", "2", yes=True)
        self.assertEqual(code, 0)
        bak = list(self.tmp.glob("config.json.bak-*"))[0]
        before = read_cfg(self.tmp)["mention"]["per_hour"]
        _, out2, _ = run_restore(self.tmp, name=bak.name)
        self.assertIn("干跑", out2)
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_hour"], before)

    def test_restore_missing_name_dies(self):
        code, _, err = run_restore(self.tmp, name="config.json.bak-不存在", yes=True)
        self.assertEqual(code, 1)
        self.assertIn("备份不存在", err)


class TestBackupRotationAndRate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_backup_rotation_keeps_10(self):
        # 手工造 12 个旧备份 → 一次 backup 后应只剩 10
        for i in range(12):
            Path(self.tmp, f"config.json.bak-20261010-{i:02d}0000").write_text("{}")
        Path(self.tmp, "config.json").write_text("{}")
        R.backup_config(self.tmp)
        self.assertEqual(len(list(self.tmp.glob("config.json.bak-*"))), 10)

    def test_rate_path_also_backs_up(self):
        out = StringIO()
        old = sys.stdout
        sys.stdout = out
        try:
            R.cmd_rate(Namespace(per_round=2, per_hour=None, per_day=None))
        finally:
            sys.stdout = old
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_round"], 2)
        self.assertEqual(len(list(self.tmp.glob("config.json.bak-*"))), 1)
        self.assertIn("已自动备份", out.getvalue())


def run_set_many(tmp, items, yes=False, approved_by="测试：老板口头批准",
                 reason=None, actor="agent"):
    out, err = StringIO(), StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    code = 0
    try:
        R.cmd_cfg_set_many(Namespace(items=items, yes=yes, approved_by=approved_by,
                                     reason=reason, actor=actor))
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.stdout, sys.stderr = old
    return code, out.getvalue(), err.getvalue()


def hist_lines(tmp):
    f = Path(tmp, "param-history.jsonl")
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()
            if line.strip()]


class TestCfgSetMany(unittest.TestCase):
    """set-many：一个意图改多项 —— 只备份 1 份、写入整体原子、账本逐项一条。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_dry_run_no_write(self):
        before = Path(self.tmp, "config.json").read_bytes()
        code, out, _ = run_set_many(self.tmp, ["mention.per_hour=2", "write.cooldown_sec=90"])
        self.assertEqual(code, 0)
        self.assertIn("干跑", out)
        self.assertIn("1 → 2", out)
        self.assertIn("120 → 90", out)
        self.assertEqual(Path(self.tmp, "config.json").read_bytes(), before)
        self.assertEqual(list(self.tmp.glob("config.json.bak-*")), [])

    def test_yes_single_backup_all_written(self):
        code, _out, _err = run_set_many(
            self.tmp, ["mention.per_hour=2", "write.cooldown_sec=90",
                       "budget.max_push_per_round=2"], yes=True)
        self.assertEqual(code, 0)
        cfg = read_cfg(self.tmp)
        self.assertEqual(cfg["mention"]["per_hour"], 2)
        self.assertEqual(cfg["write"]["cooldown_sec"], 90)
        self.assertEqual(cfg["budget"]["max_push_per_round"], 2)
        baks = list(self.tmp.glob("config.json.bak-*"))
        self.assertEqual(len(baks), 1)  # 三项改动只占 1 份备份（单条 set 要占 3 份）
        bak = json.loads(baks[0].read_text(encoding="utf-8"))
        self.assertEqual(bak["mention"]["per_hour"], 1)
        self.assertEqual(bak["write"]["cooldown_sec"], 120)

    def test_ledger_one_line_per_item(self):
        run_set_many(self.tmp, ["mention.per_hour=2", "write.cooldown_sec=90"], yes=True)
        recs = hist_lines(self.tmp)
        self.assertEqual(len(recs), 2)
        got = {(r["param"], r["before"], r["after"]) for r in recs}
        self.assertEqual(got, {("mention.per_hour", 1, 2), ("write.cooldown_sec", 120, 90)})

    def test_sensitive_needs_approval(self):
        before = Path(self.tmp, "config.json").read_bytes()
        code, _out, err = run_set_many(self.tmp, ["mention.enabled=false"], yes=True,
                                       approved_by=None)
        self.assertEqual(code, 1)
        self.assertIn("敏感项", err)
        self.assertEqual(Path(self.tmp, "config.json").read_bytes(), before)
        self.assertEqual(list(self.tmp.glob("config.json.bak-*")), [])

    def test_sensitive_with_approval_writes(self):
        code, _out, _err = run_set_many(self.tmp, ["mention.enabled=false"], yes=True,
                                        approved_by="老板：先关掉 @")
        self.assertEqual(code, 0)
        self.assertFalse(read_cfg(self.tmp)["mention"]["enabled"])
        self.assertEqual(hist_lines(self.tmp)[0]["approved_by"], "老板：先关掉 @")

    def test_bad_path_writes_nothing(self):
        before = Path(self.tmp, "config.json").read_bytes()
        code, _out, err = run_set_many(self.tmp, ["mention.per_hour=2", "mention.typo=1"],
                                       yes=True)
        self.assertEqual(code, 1)
        self.assertIn("没有 mention.typo", err)
        self.assertEqual(Path(self.tmp, "config.json").read_bytes(), before)
        self.assertEqual(list(self.tmp.glob("config.json.bak-*")), [])

    def test_duplicate_path_dies(self):
        code, _out, err = run_set_many(self.tmp, ["mention.per_hour=2", "mention.per_hour=3"],
                                       yes=True)
        self.assertEqual(code, 1)
        self.assertIn("出现两次", err)
        self.assertEqual(list(self.tmp.glob("config.json.bak-*")), [])

    def test_noop_skipped(self):
        code, out, _ = run_set_many(self.tmp, ["mention.per_hour=1"], yes=True)
        self.assertEqual(code, 0)
        self.assertIn("全部无需修改", out)
        self.assertEqual(list(self.tmp.glob("config.json.bak-*")), [])

    def test_missing_equals_dies(self):
        code, _out, err = run_set_many(self.tmp, ["mention.per_hour"], yes=True)
        self.assertEqual(code, 1)
        self.assertIn("格式应为", err)


class TestHardGateGuard(unittest.TestCase):
    """B2 硬闸阈值 11-18 起属敏感项：无老板批准不许直改。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_hard_gate_requires_approval(self):
        before = Path(self.tmp, "config.json").read_bytes()
        code, _out, err = run_set(self.tmp, "budget.min_total_score", "20", yes=True,
                                  approved_by=None)
        self.assertEqual(code, 1)
        self.assertIn("敏感项", err)
        self.assertEqual(Path(self.tmp, "config.json").read_bytes(), before)

    def test_hard_gate_with_approval_writes(self):
        code, _out, _err = run_set(self.tmp, "budget.min_total_score", "20", yes=True)
        self.assertEqual(code, 0)
        self.assertEqual(read_cfg(self.tmp)["budget"]["min_total_score"], 20)


class TestBakRotationOrder(unittest.TestCase):
    """轮转按文件名里的时间戳排（copy2 会把源 mtime 带过来，不能用 mtime 排）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_presetup_bak_rotates_by_name_timestamp(self):
        for i in range(9):
            Path(self.tmp, f"config.json.bak-20261010-{i:02d}0000").write_text("{}")
        pre = Path(self.tmp, "config.json.bak-pre-setup-20261009-100134")
        pre.write_text("{}")
        Path(self.tmp, "config.json").write_text("{}")
        R.backup_config(self.tmp)
        self.assertEqual(len(list(self.tmp.glob("config.json.bak-*"))), 10)
        self.assertFalse(pre.exists())  # 名字里时间最早 → 先被轮转掉

    def test_bak_without_timestamp_rotates_first(self):
        for i in range(10):
            Path(self.tmp, f"config.json.bak-20261010-{i:02d}0000").write_text("{}")
        weird = Path(self.tmp, "config.json.bak-junk")
        weird.write_text("{}")
        Path(self.tmp, "config.json").write_text("{}")
        R.backup_config(self.tmp)
        self.assertFalse(weird.exists())
        self.assertEqual(len(list(self.tmp.glob("config.json.bak-*"))), 10)


if __name__ == "__main__":
    unittest.main()