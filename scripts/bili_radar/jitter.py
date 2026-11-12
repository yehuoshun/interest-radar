# -*- coding: utf-8 -*-
"""jitter.py —— 巡更时刻的随机抖动（2026-11-13）。

rrule 是死的：DSH 的 schedule 只给固定时刻（`BYMINUTE=43`），每次都是同一分钟同一秒开门，
这就是机器味儿。真人不会这么准，所以每次触发后先在这里随机等一会儿再动手。

分布：三角分布（峰值 0）—— 多数巡更几乎准点，偶尔拖到十几分钟，和夜班保安一个样。
每次等待都记进 `state/jitter-log.jsonl`，事后能证明巡更时刻是散的。
"""
import json
import random
import time
from datetime import datetime

from bili_radar.core import die, state_dir

MAX_MIN = 60
LOG_NAME = "jitter-log.jsonl"


def fmt_delay(sec: int) -> str:
    if sec < 60:
        return f"{sec} 秒"
    return f"{sec // 60} 分 {sec % 60} 秒"


def pick_delay(max_min: int) -> int:
    """0..max_min 分钟之间的等待秒数（三角分布，峰值在 0）。"""
    return int(random.triangular(0, max_min * 60, 0))


def log_delay(sec: int, max_min: int, slept: bool) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "delay_sec": sec, "max_min": max_min, "slept": slept}
    with (d / LOG_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_jitter(a) -> None:
    mx = a.max_min
    if not 0 <= mx <= MAX_MIN:
        die(f"--max-min 要落在 0–{MAX_MIN}：{mx}")
    sec = pick_delay(mx)
    if a.sleep and sec:
        time.sleep(sec)
    log_delay(sec, mx, bool(a.sleep))
    print(json.dumps({"delay_sec": sec, "delay_human": fmt_delay(sec),
                      "slept": bool(a.sleep), "max_min": mx}, ensure_ascii=False))
