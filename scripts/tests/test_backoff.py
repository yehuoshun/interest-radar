"""请求层退避：指数退避时长 / 熔断 / 复位。"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from radar_lib import cli as R


class TestBackoff(unittest.TestCase):
    def setUp(self):
        R._BACKOFF["streak"] = 0

    def test_retry_sleep_exponential(self):
        with mock.patch("radar_lib.client.time.sleep") as s:
            R._retry_sleep(0)
            self.assertEqual(s.call_args[0][0], 1.5)
            R._retry_sleep(1)
            self.assertEqual(s.call_args[0][0], 3.0)
            R._retry_sleep(2)
            self.assertEqual(s.call_args[0][0], 6.0)

    def test_retry_sleep_cap_60(self):
        with mock.patch("radar_lib.client.time.sleep") as s:
            R._retry_sleep(6)  # 1.5 * 64 = 96 → cap 60
            self.assertEqual(s.call_args[0][0], 60.0)

    def test_fuse_dies_after_3(self):
        R._BACKOFF["streak"] = 2
        with self.assertRaises(SystemExit) as cm:
            R._note_fail("网络", "超时")
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual(R._BACKOFF["streak"], 3)

    def test_note_ok_resets_streak(self):
        R._BACKOFF["streak"] = 2
        R._note_ok()
        self.assertEqual(R._BACKOFF["streak"], 0)

    def test_fuse_not_triggered_below_3(self):
        R._note_fail("网络", "x")  # streak 1
        R._note_fail("网络", "x")  # streak 2 —— 不抛
        self.assertEqual(R._BACKOFF["streak"], 2)

    def test_get_business_code_no_retry(self):
        """业务 code≠0 立即 die（不重试）。"""
        def fake_urlopen(req, timeout=15):
            class Rsp:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def read(self):
                    return b""

            import io
            return io.BytesIO(b'{"code": -404, "message": "not found"}')
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen) as uo, \
             self.assertRaises(SystemExit) as cm:
            R.get("https://api.bilibili.com/x/test", "ck")
        self.assertEqual(cm.exception.code, 4)
        self.assertEqual(uo.call_count, 1)  # 只请求一次，不重试


if __name__ == "__main__":
    unittest.main()