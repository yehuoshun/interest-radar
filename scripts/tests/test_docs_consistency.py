#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_docs_consistency.py —— 文档不许跟代码漂开。

盯三件真漂过的事（2026-11 一个月内全发生过）：
① 全量用例数只在 AGENTS.md 写一次，且必须等于实际用例数；
② README 表头不许钉「截至 YYYY-MM-DD · commit」，钉了就必然过期；
③ 散文里不许复述 kind 级频控数字（11-13 全部归零、11-16 又把评论调回有限额，散文没跟上）。

口径：具体数值以 state/config.json（当前值）与 PARAMETERS.md（参数账本）为准。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def count_tests() -> int:
    """按真实的 unittest 发现机制数一遍（和 CI 跑的是同一套）。"""
    here = Path(__file__).resolve().parent
    return unittest.TestLoader().discover(str(here)).countTestCases()


class CaseCountTest(unittest.TestCase):
    def test_agents_md_states_current_count(self):
        m = re.search(r"当前 \*\*(\d+) 例\*\*", read("AGENTS.md"))
        self.assertIsNotNone(m, "AGENTS.md 里找不到「当前 **N 例**」")
        self.assertEqual(int(m.group(1)), count_tests(),
                         "AGENTS.md 的用例数与实际不符：改了测试就同步这一处")

    def test_count_not_restated_elsewhere(self):
        for rel in ("README.md", "AGENT.md", "SKILL.md", "PARAMETERS.md",
                    ".github/workflows/ci.yml"):
            text = read(rel)
            self.assertIsNone(re.search(r"全量[^\n]{0,10}\d+\s*例", text),
                              rel + " 又复述了一遍全量用例数（只留在 AGENTS.md）")
            self.assertIsNone(re.search(r"\d+\s*个?用例", text),
                              rel + " 里出现「N 用例」（只留在 AGENTS.md）")


class HeaderPinTest(unittest.TestCase):
    def test_readme_has_no_pinned_commit_header(self):
        self.assertIsNone(
            re.search(r"截至\s*\d{4}-\d{2}-\d{2}\s*[·・]?\s*commit", read("README.md")),
            "README 的「实测状态」别钉日期和 commit —— 钉了就必然过期")


class ProseNumbersTest(unittest.TestCase):
    """散文里复述 kind 级频控 = 必漂；要查值去看 PARAMETERS.md。"""

    PAT = re.compile(r"(like|comment|dynamic|message|mention)[^|\n]{0,16}"
                     r"\d+\s*(?:/|每)\s*(?:小时|天)")

    def test_no_kind_level_rate_in_prose(self):
        for rel in ("README.md", "AGENTS.md"):
            hit = self.PAT.search(read(rel))
            self.assertIsNone(hit, rel + " 复述了频控数字：" +
                              (hit.group(0) if hit else ""))


if __name__ == "__main__":
    unittest.main()
