# -*- coding: utf-8 -*-
"""plan.py —— 下一次什么时候醒（节奏只有一条：看完一条歇 1–10 分钟接着看下一条）。

口径演变（都是老板的话）：
- 13:14「不要设定阈值。你规划好刷视频的间隔就行了」
- 16:0x「你循完一次后自动设定下次唤醒时间不就行了？」→ 醒点自己写，不贴整点
- 16:2x「掷一个 50–120 分钟的随机间隔？你是不是又理解错了？」→ 对，50–120 是我拍的。
  老板给的节奏只有一条：上一次观看结束 + 1–10 分钟 = 下一次观看开始。

所以这里不排班、不打分，只做两件事：
1. `next`：拿「上一次还在 B 站」的时刻 + 1–10 分钟，算出下一次醒点，并给一条一次性闹钟的 rrule；
2. `gate`：同一分钟内重复触发就跳过（只防抖，不排班）。
"""
import argparse
import json
import random
from datetime import datetime, timedelta, timezone

from bili_radar.core import state_dir

TZ = timezone(timedelta(hours=8))

REST_MIN = 1
REST_MAX = 10
LOG_NAME = "jitter-log.jsonl"


def last_seen():
    """上一次「还在 B 站」的时刻：`state/jitter-log.jsonl` 里最后一条记录。

    开门（open）、串内歇息（rest）、收尾（close）都算 —— 因为节奏只有一条：
    上一次观看结束之后歇 1–10 分钟，下一次观看开始。
    """
    f = state_dir() / LOG_NAME
    if not f.is_file():
        return None
    ts = None
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            ts = datetime.fromisoformat(row["ts"]).replace(tzinfo=TZ)
        except (ValueError, KeyError, TypeError):
            continue
    return ts


def last_scan():
    """兼容旧名字（`last_scan` → `last_seen`）。"""
    return last_seen()


def rest_min(rng=None) -> int:
    """看完一条之后歇几分钟：1–10（老板 11-13 定死的区间，别再加别的间隔）。"""
    rng = rng or random
    return rng.randint(REST_MIN, REST_MAX)


def next_wake(now=None, rng=None):
    """下一次醒来的时刻 = 上一次还在 B 站的时刻 + 1–10 分钟。"""
    now = now or datetime.now(TZ)
    base = last_seen() or now
    wake = (base + timedelta(minutes=rest_min(rng))).replace(second=0, microsecond=0)
    if wake <= now:
        wake = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    return wake


def wake_rrule(wake) -> str:
    """一次性唤醒闹钟：`FREQ=DAILY;COUNT=1` 就是「只响这一次」。"""
    return ("DTSTART;TZID=Asia/Shanghai:%s\nRRULE:FREQ=DAILY;COUNT=1"
            % wake.strftime("%Y%m%dT%H%M%S"))


def gate(now=None) -> dict:
    """这一分钟该不该开刷：同一分钟内重复触发就跳过（防抖，不是排班）。"""
    now = now or datetime.now(TZ)
    last = last_seen()
    gap = REST_MIN
    if last is None:
        return {"allowed": True, "reason": "没有上一巡记录，直接开刷",
                "since_last_min": None, "min_gap_min": gap,
                "next_allowed": now.replace(second=0, microsecond=0).isoformat()}
    since = int((now - last).total_seconds() // 60)
    ok = since >= gap
    return {
        "allowed": ok,
        "reason": ("距上一条记录 %d 分钟" % since if ok
                   else "距上一条记录只有 %d 分钟（同一分钟重复触发），这一巡跳过" % since),
        "since_last_min": since,
        "min_gap_min": gap,
        "last_scan": last.isoformat(),
        "next_allowed": (now if ok else last + timedelta(minutes=gap)).replace(
            second=0, microsecond=0).isoformat(),
    }


def describe() -> str:
    return ("节奏：上一次观看结束 + %d–%d 分钟 = 下一次观看开始（醒点自己写一次性闹钟，不排班）；"
            "gate 只防同一分钟重复触发" % (REST_MIN, REST_MAX))


def main():
    ap = argparse.ArgumentParser(description="下次什么时候醒（plan.py）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gate", help="这一巡该不该开刷（防重复触发，JSON）")
    sub.add_parser("next", help="算下一次醒点（上一次记录 + 1–10 分钟）并给一次性 rrule")
    sub.add_parser("describe", help="当前节奏的一句话说明")
    a = ap.parse_args()

    if a.cmd == "gate":
        print(json.dumps(gate(), ensure_ascii=False, indent=2))
    elif a.cmd == "next":
        now = datetime.now(TZ)
        base = last_seen()
        wake = next_wake(now)
        pushed = bool(base and base + timedelta(minutes=REST_MIN) <= now)
        print(json.dumps({
            "wake_at": wake.isoformat(),
            "from": base.isoformat() if base else None,
            "gap_min": None if pushed else int((wake - base).total_seconds() // 60),
            "reason": ("上一条记录已经过去很久，顺延到下一分钟" if pushed
                       else "上一次记录 + %d 分钟" % int((wake - (base or now)).total_seconds() // 60)),
            "rrule": wake_rrule(wake),
        }, ensure_ascii=False, indent=2))
    else:
        print(describe())


if __name__ == "__main__":
    main()
