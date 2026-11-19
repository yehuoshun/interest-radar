#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_text_fold.py —— 字幕折行 + 入口脚本 UTF-8。

来由（2026-11-19 第 19 巡）：① `sub` 的 text 是 5199 字一整行，read 工具按单行 2000 字截断，
一条字幕得先自己折一遍；② Windows 控制台默认 GBK，中文里的 \xa0 之类会让 print 崩掉，
而当时只有 radar.py / plan.py 两个入口改了 UTF-8，frames / schedule / init / 扫码登录 都没改。
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

from bili_radar import cli, core
from bili_radar.browse import _break_index, fold_text

SCRIPTS = Path(__file__).resolve().parents[1]


class FoldTextTest(unittest.TestCase):
    def test_no_char_lost(self):
        text = "第一句话，这里有个逗号。第二句话呢？第三句没有了；最后一段也说完了！"
        folded = fold_text(text, 12)
        self.assertEqual(folded.replace("\n", ""), text, "折行不许删字或改字")

    def test_every_line_within_width(self):
        text = "啊" * 137
        for line in fold_text(text, 10).split("\n"):
            self.assertLessEqual(len(line), 10)

    def test_prefers_sentence_end(self):
        text = "这是第一句，用来测试折行的句子边界。" * 3
        lines = fold_text(text, 30).split("\n")
        self.assertTrue(lines[0].endswith("。"), lines[0])
        self.assertEqual(lines[0], "这是第一句，用来测试折行的句子边界。")

    def test_hard_cut_when_no_punctuation(self):
        lines = fold_text("啊" * 95, 10).split("\n")
        self.assertEqual([len(l) for l in lines], [10] * 9 + [5])

    def test_short_text_stays_one_line(self):
        self.assertEqual(fold_text("很短的一条", 80), "很短的一条")

    def test_width_zero_returns_raw(self):
        text = "一整行不折。这里还有第二句。"
        self.assertEqual(fold_text(text, 0), text)

    def test_empty_text(self):
        self.assertEqual(fold_text("", 20), "")

    def test_break_index_falls_back_to_width(self):
        self.assertEqual(_break_index("abcdefgh", 8), 8)


class Utf8StdoutTest(unittest.TestCase):
    class _Fake:
        def __init__(self):
            self.calls = []

        def reconfigure(self, **kw):
            self.calls.append(kw)

    def test_reconfigures_both_streams(self):
        out, err = self._Fake(), self._Fake()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            core.enable_utf8_stdout()
        for s in (out, err):
            self.assertEqual(s.calls, [{"encoding": "utf-8", "errors": "replace"}])

    def test_stream_without_reconfigure_is_skipped(self):
        plain = object()  # 测试里 sys.stdout 常被换成 StringIO / 裸对象
        with mock.patch.object(sys, "stdout", plain), mock.patch.object(sys, "stderr", plain):
            core.enable_utf8_stdout()  # 不抛就是通过


class EntryShellTest(unittest.TestCase):
    def test_every_entry_script_enables_utf8(self):
        missing = [p.name for p in sorted(SCRIPTS.glob("*.py"))
                   if "enable_utf8_stdout" not in p.read_text(encoding="utf-8")]
        self.assertEqual(missing, [], "这些入口脚本没走 enable_utf8_stdout，GBK 控制台下会崩")


class SubWrapFlagTest(unittest.TestCase):
    def test_default_wrap_is_80(self):
        a = cli.build_parser().parse_args(["sub", "BV1xxx"])
        self.assertEqual(a.wrap, 80)
        self.assertEqual(a.max_chars, 6000)

    def test_wrap_can_be_disabled(self):
        a = cli.build_parser().parse_args(["sub", "BV1xxx", "--wrap", "0"])
        self.assertEqual(a.wrap, 0)


if __name__ == "__main__":
    unittest.main()
