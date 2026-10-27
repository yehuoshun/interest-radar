"""dm 水位回归（#8）：水位只按主号消息推进；new_only 不输出自己消息；主号回复不丢。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import radar as R

MID, ME = 239028467, 111


def _msg(ts, sender, text):
    return {"timestamp": ts, "sender_uid": sender,
            "content": json.dumps({"content": text})}


class TestDmWatermark(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["INTERESTS_DIR"] = self.tmp
        for target, se in [
            ("notify.load_cookie", lambda: "ck"),
            ("notify.read_config", lambda: {"mention": {"mid": MID}}),
        ]:
            p = mock.patch(target, side_effect=se)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def _state(self):
        return Path(self.tmp, "dm-state.json")

    def _run(self, msgs, new_only=True):
        def fake_get(url, cookie, tries=3):
            if "nav" in url:
                return {"data": {"mid": ME}}
            return {"data": {"messages": msgs}}
        with mock.patch("notify.get", side_effect=fake_get):
            a = SimpleNamespace(mid=None, size=20, new_only=new_only)
            captured = {}
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                R.cmd_dm(a)
            return json.loads(buf.getvalue())

    def test_watermark_only_advances_on_owner_msg(self):
        """自己消息不推水位（核心回归）。"""
        out = self._run([_msg(100, MID, "旧"), _msg(105, MID, "主号回复"),
                         _msg(108, ME, "我发的私信")])
        self.assertEqual(out["water_level"], 105)  # 不是 108

    def test_new_only_excludes_own_messages(self):
        out = self._run([_msg(100, MID, "旧"), _msg(105, MID, "主号回复"),
                         _msg(108, ME, "我发的私信")])
        texts = [m["text"] for m in out["messages"]]
        self.assertIn("主号回复", texts)
        self.assertNotIn("我发的私信", texts)

    def test_owner_reply_after_own_msg_not_lost(self):
        """第一轮水位 105；第二轮主号回 110 → 必须读到。"""
        self._run([_msg(100, MID, "旧"), _msg(105, MID, "主号回复"), _msg(108, ME, "我的")])
        # 第二轮
        out2 = self._run([_msg(105, MID, "旧主号"), _msg(108, ME, "我的"),
                          _msg(110, MID, "主号新回复")])
        self.assertEqual(out2["water_level"], 110)
        texts = [m["text"] for m in out2["messages"]]
        self.assertEqual(texts, ["主号新回复"])

    def test_owner_reply_before_own_msg_visible_this_round(self):
        """主号在我发消息前回复，本轮必须输出（不被水位提前挡掉）。"""
        out = self._run([_msg(105, MID, "主号提前回复"), _msg(108, ME, "我的")])
        texts = [m["text"] for m in out["messages"]]
        self.assertIn("主号提前回复", texts)

    def test_no_new_no_state_write(self):
        """水位没动就不写状态文件（避免无谓 IO）。"""
        self._run([_msg(100, MID, "旧")])  # 第一轮：建 state，水位 100
        self.assertTrue(self._state().exists())
        mtime = self._state().stat().st_mtime
        # 第二轮：无新主号消息 → 不重写
        self._run([_msg(100, MID, "旧")])
        self.assertEqual(self._state().stat().st_mtime, mtime)


if __name__ == "__main__":
    unittest.main()