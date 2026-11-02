"""B3（2026-11-02）原子写 + 乐观锁：tmp+os.replace+并发检测重试。

关键场景：mutate 执行期间别人改了 config.json → 必须重读重试，且并发者的修改
不能丢；持续冲突 → die(9)；mutate 返回 None → 不写。
"""
import json
import os
import sys
import tempfile
import time
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bili_radar import cli as R
from bili_radar.gates import atomic_write_config

CONFIG = {
    "mention": {"per_hour": 1, "name": "夜灬瞬"},
    "write": {"message": {"enabled": True}},
}


def setup(tmp: Path):
    Path(tmp, "config.json").write_text(json.dumps(CONFIG, ensure_ascii=False, indent=2)
                                        + "\n", encoding="utf-8")


def read_cfg(tmp):
    return json.loads(Path(tmp, "config.json").read_text(encoding="utf-8"))


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["INTERESTS_DIR"] = str(self.tmp)
        setup(self.tmp)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def test_basic_write_and_no_tmp_left(self):
        R.atomic_write_config(self.tmp, lambda c: {**c, "x": 1})
        self.assertEqual(read_cfg(self.tmp)["x"], 1)
        self.assertEqual(list(self.tmp.glob("config.json.tmp-*")), [])

    def test_mutate_none_means_no_write(self):
        p = self.tmp / "config.json"
        before = p.stat().st_mtime_ns
        time.sleep(0.002)
        R.atomic_write_config(self.tmp, lambda c: None)
        self.assertEqual(p.stat().st_mtime_ns, before)
        # 内容也没变
        self.assertEqual(read_cfg(self.tmp), CONFIG)

    def test_concurrent_edit_survives_retry(self):
        calls = {"n": 0}

        def mutate(c):
            calls["n"] += 1
            if calls["n"] == 1:
                # 模拟并发：mutate 期间别人改了文件
                p = self.tmp / "config.json"
                cur = json.loads(p.read_text(encoding="utf-8"))
                cur["intruder"] = True
                p.write_text(json.dumps(cur), encoding="utf-8")
                os.utime(p, None)
            return {**c, "mine": 1}

        atomic_write_config(self.tmp, mutate)
        cfg = read_cfg(self.tmp)
        self.assertEqual(cfg["mine"], 1)            # 我的修改在
        self.assertTrue(cfg.get("intruder"))        # 并发者的修改没丢
        self.assertEqual(calls["n"], 2)            # 恰好重试了一次

    def test_persistent_conflict_dies_9(self):
        n = {"v": 0}

        def mutate(c):
            # 每次篡改都写出新内容 → 永远冲突
            n["v"] += 1
            p = self.tmp / "config.json"
            cur = json.loads(p.read_text(encoding="utf-8"))
            cur["intruder"] = n["v"]
            p.write_text(json.dumps(cur), encoding="utf-8")
            return {**c, "x": 1}

        with self.assertRaises(SystemExit) as cm:
            atomic_write_config(self.tmp, mutate)
        self.assertEqual(cm.exception.code, 9)

    def test_set_via_atomic_end_to_end(self):
        """回归：cfg_tool.cmd_cfg_set 走 atomic 后行为不变。"""
        R.cmd_cfg_set(Namespace(path="mention.per_hour", value="2", yes=True,
                                reason=None, actor="agent", approved_by="测试：老板口头批准"))
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_hour"], 2)
        self.assertEqual(list(self.tmp.glob("config.json.tmp-*")), [])

    def test_rate_via_atomic_end_to_end(self):
        """回归：rate 写路径走 atomic 后行为不变。"""
        R.cmd_rate(Namespace(per_round=None, per_hour=2, per_day=None))
        self.assertEqual(read_cfg(self.tmp)["mention"]["per_hour"], 2)
        rows = [json.loads(l) for l in
                Path(self.tmp, "param-history.jsonl").read_text(encoding="utf-8").splitlines()
                if l.strip()]
        self.assertEqual(rows[-1]["after"], 2)


if __name__ == "__main__":
    unittest.main()