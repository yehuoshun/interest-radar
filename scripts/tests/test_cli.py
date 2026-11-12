"""CLI 参数表回归：报错文案里提到的开关，必须真的存在。

来由（2026-11-13）：`config set` 的敏感项闸在 stderr 里教用户「加 --approved-by "老板原话"」，
但 cli 的 `config set` 解析器根本没注册这个参数 —— 照着文档做会得到
`radar.py: error: unrecognized arguments: --approved-by …`，闸门等于死路。
"""
import unittest

from bili_radar import cli


class TestSensitiveGateFlags(unittest.TestCase):
    def test_config_set_accepts_approved_by(self):
        a = cli.build_parser().parse_args(
            ["config", "set", "write.cooldown_sec", "60", "--yes",
             "--approved-by", "设置冷却1min"])
        self.assertEqual(a.cfg_action, "set")
        self.assertEqual(a.path, "write.cooldown_sec")
        self.assertEqual(a.value, "60")
        self.assertTrue(a.yes)
        self.assertEqual(a.approved_by, "设置冷却1min")

    def test_approved_by_defaults_to_none(self):
        a = cli.build_parser().parse_args(["config", "set", "mention.name", "某人", "--yes"])
        self.assertIsNone(a.approved_by)

    def test_propose_flow_still_available(self):
        # 没老板批准时的正规路径：propose → approve/reject
        a = cli.build_parser().parse_args(["config", "propose", "write.cooldown_sec", "60"])
        self.assertEqual(a.cfg_action, "propose")


if __name__ == "__main__":
    unittest.main()
