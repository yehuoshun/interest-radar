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


def run_set(tmp, path, value, yes=False):
    out, err = StringIO(), StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    code = 0
    try:
        R.cmd_cfg_set(Namespace(path=path, value=value, yes=yes))
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


if __name__ == "__main__":
    unittest.main()