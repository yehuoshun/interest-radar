# -*- coding: utf-8 -*-
"""jitter.py —— 巡更开门 / 看片计时 / 串内歇息 / 收尾打卡（2026-11-13）。

四个用途：

0. **看片计时**（`--watch 315 --sleep`）：把这条视频的时长真的花掉。
   11-13 17:07 老板：「是视频时长 + 一到十分钟」，不是光歇 1–10 分钟 ——
   不看片就没有「8 分钟」这段，节奏会退化成每两三分钟一巡。所以每看一条，
   先用时长（秒）记一笔 `kind=watch`，收尾时刻才落在「看完」之后。

1. **巡更开门**（默认）：rrule 是死的（整点 `BYMINUTE=0`），触发后先随机等 0–10 分钟再动手，
   三角分布、峰值 0 —— 多数几乎准点，偶尔拖到接近上限，和夜班保安一个样。
2. **串内歇息**（`--min-min 1 --max-min 10 --rest`）：看完一条视频，歇 1–10 分钟再看下一条，
   均匀分布。11-13 老板：「每看完一条，歇 1–10 分钟接着看下一条」。
3. **收尾打卡**（`--close`）：一串看到自然想走时记一笔，不等待。巡更护栏从「收尾」而不是
   「开门」开始算 —— 我看了 30 分钟才关掉，那 30 分钟也算刷过了，不该按开门时间倒推。

每次等待都记进 `state/jitter-log.jsonl`，带 `kind`：`open`（巡更开门）/ `watch`（看片，花掉时长）/
`rest`（串内歇息）/ `close`（一串结束）。`plan.py gate` 认 `open` 和 `close`、不认 `rest` ——
歇息是串里的呼吸，收尾是「我离开 B 站了」，后者才是巡更间隔的起点。
"""
import json
import random
import time
from datetime import datetime

from bili_radar.core import die, state_dir

MAX_MIN = 60
MAX_WATCH_SEC = 7200
LOG_NAME = "jitter-log.jsonl"
KIND_OPEN = "open"
KIND_WATCH = "watch"
KIND_REST = "rest"
KIND_CLOSE = "close"


def fmt_delay(sec: int) -> str:
    if sec < 60:
        return f"{sec} 秒"
    return f"{sec // 60} 分 {sec % 60} 秒"


def pick_delay(max_min: int, min_min: int = 0) -> int:
    """等待秒数。min_min=0 → 三角分布（峰值 0）；min_min>0 → [min,max] 均匀分布。"""
    if min_min > 0:
        return int(random.uniform(min_min * 60, max_min * 60))
    return int(random.triangular(0, max_min * 60, 0))


def log_delay(sec: int, max_min: int, slept: bool,
              kind: str = KIND_OPEN, min_min: int = 0) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "delay_sec": sec, "max_min": max_min, "min_min": min_min,
           "kind": kind, "slept": slept}
    with (d / LOG_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def fmt_watch(sec: int) -> str:
    """把视频时长写成 H:MM:SS 或 M:SS（和 B 站上看到的一样）。"""
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def log_watch(sec: int, slept: bool) -> None:
    """记一笔「看这条花了多久」：kind=watch，dur_sec=视频时长。"""
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "kind": KIND_WATCH, "dur_sec": int(sec), "slept": slept}
    with (d / LOG_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_jitter(a) -> None:
    mx = a.max_min
    mn = getattr(a, "min_min", 0)
    rest = bool(getattr(a, "rest", False))
    close = bool(getattr(a, "close", False))
    watch = int(getattr(a, "watch", 0) or 0)
    if rest and close:
        die("--rest（歇息）和 --close（收尾）只能选一个")
    if watch:
        if rest or close:
            die("--watch（看片计时）不能和 --rest / --close 同时用")
        if not 0 < watch <= MAX_WATCH_SEC:
            die(f"--watch 要 1–{MAX_WATCH_SEC} 秒：{watch}")
        if a.sleep:
            time.sleep(watch)
        log_watch(watch, bool(a.sleep))
        print(json.dumps({"kind": KIND_WATCH, "dur_sec": watch,
                          "dur_human": fmt_watch(watch), "slept": bool(a.sleep)},
                         ensure_ascii=False))
        return
    if close:
        log_delay(0, 0, False, KIND_CLOSE)
        print(json.dumps({"kind": KIND_CLOSE, "delay_sec": 0, "slept": False},
                         ensure_ascii=False))
        return
    kind = KIND_REST if rest else KIND_OPEN
    if not 0 <= mn <= mx <= MAX_MIN:
        die(f"要满足 0 ≤ --min-min ≤ --max-min ≤ {MAX_MIN}：{mn} / {mx}")
    sec = pick_delay(mx, mn)
    if a.sleep and sec:
        time.sleep(sec)
    log_delay(sec, mx, bool(a.sleep), kind, mn)
    print(json.dumps({"kind": kind, "delay_sec": sec, "delay_human": fmt_delay(sec),
                      "slept": bool(a.sleep), "min_min": mn, "max_min": mx},
                     ensure_ascii=False))
