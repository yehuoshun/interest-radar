#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""radar.py —— 兴趣雷达 CLI 入口（薄壳）。

实现全在 bili_radar/ 包里（零 __init__.py，隐式命名空间包）：
  core / client / gates / browse / comment / draft / notify / dynamic / feedback / cli / media/

用法不变：python scripts/radar.py <子命令> ...
"""
import sys
from pathlib import Path

# Windows 下 stdout 默认按 GBK 编码，遇到非 GBK 字符（B 站文案里的 \xa0 之类）会直接
# UnicodeEncodeError 崩掉整条命令。入口处统一改成 UTF-8，坏字节退化成替换符而不是中断。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bili_radar.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
