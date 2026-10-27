"""draft 状态机：new 校验（字数/敏感词/水军昵称/同人限频）/ 过期作废 / 频控 / approve 发送。"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bili_radar import cli as R


BASE_CFG = {
    "draft": {"enabled": True, "per_12h": 1, "per_24h": 2, "reply_interval_days": 30,
              "forbid": ["兴趣档案"]},
    "mention": {"mid": 239028467},
    "comment_check": {"name_keywords": ["大肥鱼", "肥鱼"]},
}


class DraftBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["INTERESTS_DIR"] = self.tmp
        # 测试必须自带假 cookie：approve 路径里的 cookie_path().read_text() 没有被 mock，
        # 之前靠本机 ~/.openclaw/secrets/bilibili-cookies.txt 恰好存在才绿 —— CI 上直接 FileNotFoundError。
        self._fake_cookie = Path(self.tmp, "fake-cookie.txt")
        self._fake_cookie.write_text("SESSDATA=fake; bili_jct=fakejct; buvid3=fake\n", encoding="utf-8")
        self._recs = []
        for mock_target, side_effect in [
            ("bili_radar.draft.read_config", lambda: BASE_CFG),
            ("bili_radar.draft.load_cookie", lambda: "ck"),
            ("bili_radar.draft.cookie_path", lambda: self._fake_cookie),
            ("bili_radar.draft.csrf_from_cookie", lambda raw: "jct"),
        ]:
            p = mock.patch(mock_target, side_effect=side_effect)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        os.environ.pop("INTERESTS_DIR", None)

    def _drafts_file(self):
        return Path(self.tmp, "drafts.jsonl")

    def _seed_sent(self, frm, days_ago=25, ts=None):
        rec = {"id": "old-1", "bv": "BV1", "rpid": "1", "from": frm, "text": "x",
               "status": "sent",
               "created_at": (datetime.now() - timedelta(days=days_ago)).isoformat(),
               "sent_at": (datetime.now() - timedelta(days=days_ago)).isoformat()}
        with self._drafts_file().open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _new(self, text="这个视频怎么拍的？", from_uname="路人乙", **kw):
        a = SimpleNamespace(action="new", bv="BV2", rpid="2", from_uname=from_uname,
                            text=text, id=None, pending=False,
                            yes=False, days=None, **kw)
        R.cmd_draft(a)

    def _approve(self, yes=False):
        a = SimpleNamespace(action="approve", id=self._last_id(), from_uname=None,
                            bv=None, rpid=None, text=None, pending=False, yes=yes, days=None)
        R.cmd_draft(a)

    def _last_id(self):
        recs = [json.loads(l) for l in self._drafts_file().read_text().splitlines() if l.strip()]
        return recs[-1]["id"]


class TestDraftNew(DraftBase):
    def test_new_creates_pending(self):
        self._new()
        recs = [json.loads(l) for l in self._drafts_file().read_text().splitlines() if l.strip()]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["status"], "pending")

    def test_new_too_long_rejected(self):
        with self.assertRaises(SystemExit):
            self._new(text="长" * 151)

    def test_new_forbid_rejected(self):
        with self.assertRaises(SystemExit):
            self._new(text="我的兴趣档案是机密")

    def test_new_waterarmy_nick_rejected(self):
        with self.assertRaises(SystemExit):
            self._new(from_uname="大肥鱼666")

    def test_new_same_person_30d_rejected(self):
        import contextlib
        import io
        self._seed_sent("路人乙", days_ago=10)
        with self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self._new()
        self.assertIn("同人限频", err.getvalue())

    def test_new_same_person_after_30d_allowed(self):
        self._seed_sent("路人乙", days_ago=40)
        self._new()  # 不抛即过


class TestDraftApprove(DraftBase):
    def test_expired_after_24h(self):
        import contextlib
        import io
        self._new()
        recs = [json.loads(l) for l in self._drafts_file().read_text().splitlines() if l.strip()]
        recs[0]["created_at"] = (datetime.now() - timedelta(hours=25)).isoformat()
        self._drafts_file().write_text(json.dumps(recs[0], ensure_ascii=False) + "\n")
        with self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self._approve()
        self.assertIn("自动作废", err.getvalue())
        recs = [json.loads(l) for l in self._drafts_file().read_text().splitlines() if l.strip()]
        self.assertEqual(recs[0]["status"], "expired")

    def test_approve_dry_run(self):
        self._new()
        with mock.patch("bili_radar.draft.get", return_value={"data": {"aid": 42}}) as g:
            self._approve(yes=False)  # 不抛
            self.assertTrue(g.called)  # view 查了，但没发
        recs = [json.loads(l) for l in self._drafts_file().read_text().splitlines() if l.strip()]
        self.assertEqual(recs[0]["status"], "pending")

    def test_approve_sends_and_marks_sent(self):
        self._new()
        with mock.patch("bili_radar.draft.get", return_value={"data": {"aid": 42}}), \
             mock.patch("bili_radar.draft.post_reply", return_value={"code": 0, "data": {"rpid_str": "999"}}):
            self._approve(yes=True)
        recs = [json.loads(l) for l in self._drafts_file().read_text().splitlines() if l.strip()]
        self.assertEqual(recs[0]["status"], "sent")
        self.assertEqual(recs[0]["sent_rpid"], "999")

    def test_approve_failure_counts(self):
        self._new()
        for _ in range(2):
            with mock.patch("bili_radar.draft.get", return_value={"data": {"aid": 42}}), \
                 mock.patch("bili_radar.draft.post_reply", return_value={"code": -400, "message": "bad"}):
                with self.assertRaises(SystemExit):
                    self._approve(yes=True)
        # 第 3 次失败 → failed
        with mock.patch("bili_radar.draft.get", return_value={"data": {"aid": 42}}), \
             mock.patch("bili_radar.draft.post_reply", return_value={"code": -400, "message": "bad"}):
            with self.assertRaises(SystemExit):
                self._approve(yes=True)
        recs = [json.loads(l) for l in self._drafts_file().read_text().splitlines() if l.strip()]
        self.assertEqual(recs[0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()