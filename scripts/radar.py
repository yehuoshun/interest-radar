#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""radar.py —— 兴趣雷达 CLI 入口（薄壳）。

实现全在 bili_radar/ 包里（零 __init__.py，隐式命名空间包）：
  core / client / gates / browse / comment / draft / notify / dynamic / feedback / cli / media/

用法不变：python3 scripts/radar.py <子命令> ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bili_radar.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
