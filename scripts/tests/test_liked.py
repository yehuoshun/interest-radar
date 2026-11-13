"""`liked`（2026-11-14）：平台侧查已赞，用来跳过已点赞的视频。零网络。

老板口径：已点赞的视频也跳过；判断「是不是已读」不再扫本地 seen 文件。
"""
import json
import os
import sys
import unittest
from argparse import Namespace
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bili_radar import browse, cli


def run(bv="BV1", data=0):
    out = StringIO()
    old = sys.stdout
    sys.stdout = out
    try:
        with mock.patch("bili_radar.browse.load_cookie", return_value="SESSDATA=x"), \
             mock.patch("bili_radar.browse.get",
                        return_value={"code": 0, "data": data}) as g:
            browse.cmd_liked(Namespace(bv=bv))
    finally:
        sys.stdout = old
    return json.loads(out.getvalue()), g.call_args[0][0]


class TestLiked(unittest.TestCase):
    def test_liked_true(self):
        got, url = run(data=1)
        self.assertEqual(got, {"bvid": "BV1", "liked": True})
        self.assertIn("/x/web-interface/archive/has/like?bvid=BV1", url)

    def test_liked_false(self):
        got, _ = run(data=0)
        self.assertFalse(got["liked"])

    def test_cli_registers_liked(self):
        a = cli.build_parser().parse_args(["liked", "--bv", "BV1"])
        self.assertEqual(a.cmd, "liked")
        self.assertEqual(a.bv, "BV1")
        self.assertIs(a.fn, browse.cmd_liked)


if __name__ == "__main__":
    unittest.main()
