#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""frames.py —— 抽帧 CLI 入口（薄壳）。

实现：bili_radar/media/frames.py（流程）+ bili_radar/media/mp4_sparse.py（稀疏下载）

用法不变：python3 scripts/frames.py --bv BV1xxx [--strip] ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bili_radar.media.frames import main  # noqa: E402

if __name__ == "__main__":
    main()
