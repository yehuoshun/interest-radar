# -*- coding: utf-8 -*-
"""plan.py —— 值班节奏（2026-11-13）。

老板口径：「不要设定阈值。你规划好刷视频的间隔就行了」。
所以这里不做内容打分，只做一件事：**排好一天刷几次、每次隔多久**，以及判断
「现在这一巡该不该真刷」——距离上一巡太近就静默跳过，不为了打卡硬刷。

节奏（可从常量改）：
- 夜里 22:00–05:00：每小时一次（夜里最清醒，也最容易漏东西）
- 白天 08:00–21:00：每 2 小时一次
- 06:00–07:00：睡，不排班
两级最小间隔是「防连刷」的护栏：白天 100 分钟、夜里 50 分钟。触发时刻由 rrule 给，
护栏负责在重叠/手贱时把手按住。
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bili_radar.core import REPO_ROOT, state_dir

TZ = timezone(timedelta(hours=8))

DAY_HOURS = [8, 10, 12, 14, 16, 18, 20]
NIGHT_HOURS = [22, 23, 0, 1, 2, 3, 4, 5]
DAY_GAP_MIN = 100
NIGHT_GAP_MIN = 50
LOG_NAME = "jitter-log.jsonl"


def is_night(hour: int) -> bool:
    return hour >= 22 or hour <= 5


def required_gap(hour: int) -> int:
    return NIGHT_GAP_MIN if is_night(hour) else DAY_GAP_MIN


def hours() -> list:
    """排班的整点（升序），喂给 rrule 的 BYHOUR。"""
    return sorted(DAY_HOURS + NIGHT_HOURS)


def next_hour(now=None) -> datetime:
    """下一次排班整点（不含秒级抖动）。"""
    now = now or datetime.now(TZ)
    now = now.replace(second=0, microsecond=0)
    for step in range(0, 26):
        cand = (now + timedelta(hours=step)).replace(minute=0)
        if cand > now and cand.hour in hours():
            return cand
    return now.replace(hour=hours()[0], minute=0) + timedelta(days=1)


def last_scan() -> datetime:
    """上一次真开刷的时间：`state/jitter-log.jsonl` 的最后一条（抖动必记）。"""
    f = state_dir() / LOG_NAME
    if not f.is_file():
        return None
    ts = None
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ts = datetime.fromisoformat(json.loads(line)["ts"]).replace(tzinfo=TZ)
        except (ValueError, KeyError, TypeError):
            continue
    return ts


def gate(now=None) -> dict:
    """这一巡该不该刷：距上一巡不足最小间隔就静默。"""
    now = now or datetime.now(TZ)
    last = last_scan()
    gap = required_gap(now.hour)
    if last is None:
        return {"allowed": True, "reason": "没有上一巡记录，照排班开刷",
                "since_last_min": None, "min_gap_min": gap,
                "next_allowed": now.replace(second=0, microsecond=0).isoformat()}
    since = int((now - last).total_seconds() // 60)
    ok = since >= gap
    next_ok = last + timedelta(minutes=gap)
    return {
        "allowed": ok,
        "reason": ("距上一巡 %d 分钟，够 %d 分钟的间隔" % (since, gap) if ok
                   else "距上一巡只有 %d 分钟（护栏 %d 分钟），这一巡静默" % (since, gap)),
        "since_last_min": since,
        "min_gap_min": gap,
        "last_scan": last.isoformat(),
        "next_allowed": (now if ok else next_ok).replace(second=0, microsecond=0).isoformat(),
    }


def rrule(now=None) -> str:
    nxt = next_hour(now)
    byhour = ",".join(str(h) for h in hours())
    return ("DTSTART;TZID=Asia/Shanghai:%s\nRRULE:FREQ=DAILY;BYHOUR=%s;BYMINUTE=0"
            % (nxt.strftime("%Y%m%dT%H%M%S"), byhour))


def describe() -> str:
    return ("夜里 22–05 每小时一次、白天 08–21 每 2 小时一次、06–07 睡；"
            "护栏：夜里 ≥%d 分钟、白天 ≥%d 分钟才刷下一巡（不做内容打分）"
            % (NIGHT_GAP_MIN, DAY_GAP_MIN))


def main():
    ap = argparse.ArgumentParser(description="值班节奏：排班 + 该不该刷（plan.py）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gate", help="这一巡该不该刷（JSON）")
    sub.add_parser("rrule", help="打印排班 rrule（喂给 schedule_create）")
    sub.add_parser("hours", help="打印排班整点")
    a = ap.parse_args()

    if a.cmd == "gate":
        print(json.dumps(gate(), ensure_ascii=False, indent=2))
    elif a.cmd == "rrule":
        print(rrule())
    else:
        print(json.dumps({"hours": hours(), "plan": describe()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
