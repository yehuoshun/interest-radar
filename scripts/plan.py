# -*- coding: utf-8 -*-
"""plan.py —— 值班节奏（2026-11-13：全天每小时一巡）。

口径演变（都是老板的话）：
- 12:10「白天也继续吧，改成24小时」
- 13:14「不要设定阈值。你规划好刷视频的间隔就行了」→ 我先把白天放宽成每 2 小时
- 14:02 老板选「2」（回到全天每小时）→ 24 巡/天，白天也每小时

所以这里不做内容打分，只做两件事：排一天的整点、判断「现在这一巡该不该真刷」。
护栏 50 分钟：整点触发 + 0–10 分钟抖动，相邻两巡实际隔 50–70 分钟；
护栏只在「重叠触发 / 手贱连刷」时把手按住，不参与内容判断。
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bili_radar.core import REPO_ROOT, state_dir

TZ = timezone(timedelta(hours=8))

HOURS = list(range(24))
GAP_MIN = 50
GAP_MAX_MIN = 120
GAP_MODE_MIN = 60
LOG_NAME = "jitter-log.jsonl"


def hours() -> list:
    """排班的整点（升序），喂给 rrule 的 BYHOUR。"""
    return list(HOURS)


def next_hour(now=None) -> datetime:
    """下一次排班整点（不含秒级抖动）。"""
    now = now or datetime.now(TZ)
    now = now.replace(second=0, microsecond=0)
    cand = (now + timedelta(hours=1)).replace(minute=0)
    return cand


def last_scan() -> datetime:
    """上一巡的锚点：`state/jitter-log.jsonl` 里最后一条 `open` 或 `close`。

    - `rest`（串内歇息）跳过 —— 那是「看完一条歇 1–10 分钟」，不该喂饱巡更护栏。
    - `close`（一串收尾）算 —— 我看了半小时才关掉，那半小时也算刷过了，
      间隔要从离开 B 站那一刻开始算，不能从开门时间倒推。
    老记录没有 `kind` 字段，一律当 open。
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
            if row.get("kind", "open") == "rest":
                continue
            ts = datetime.fromisoformat(row["ts"]).replace(tzinfo=TZ)
        except (ValueError, KeyError, TypeError):
            continue
    return ts


def gate(now=None) -> dict:
    """这一巡该不该刷：距上一巡不足最小间隔就静默。"""
    now = now or datetime.now(TZ)
    last = last_scan()
    gap = GAP_MIN
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


def pick_gap_min(rng=None) -> int:
    """下一次醒来的间隔（分钟）：50–120，多数落在 60 上下（三角分布）。

    人不是「整点报到」：这次看完可能一小时后才想起来，也可能一个半小时。
    所以间隔自己掷，掷完写成下一次的闹钟 —— 醒点由上一次收尾时间推出来，不贴整点。
    """
    import random
    rng = rng or random
    return int(round(rng.triangular(GAP_MIN, GAP_MAX_MIN, GAP_MODE_MIN)))


def next_wake(now=None, rng=None) -> datetime:
    """下一次该醒来的时刻 = 上一巡锚点（开门或收尾）+ 随机间隔。"""
    now = now or datetime.now(TZ)
    base = last_scan() or now
    wake = (base + timedelta(minutes=pick_gap_min(rng))).replace(second=0, microsecond=0)
    if wake <= now:
        wake = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    return wake


def wake_rrule(wake: datetime) -> str:
    """一次性唤醒闹钟：`FREQ=DAILY;COUNT=1` 就是「只响这一次」。"""
    return ("DTSTART;TZID=Asia/Shanghai:%s\nRRULE:FREQ=DAILY;COUNT=1"
            % wake.strftime("%Y%m%dT%H%M%S"))


def rrule(now=None) -> str:
    nxt = next_hour(now)
    byhour = ",".join(str(h) for h in hours())
    return ("DTSTART;TZID=Asia/Shanghai:%s\nRRULE:FREQ=DAILY;BYHOUR=%s;BYMINUTE=0"
            % (nxt.strftime("%Y%m%dT%H%M%S"), byhour))


def describe() -> str:
    return ("全天每小时一巡（%d 巡/天，12:10「改成24小时」+ 14:02 选「2」）；"
            "护栏：距上一巡 ≥%d 分钟才刷下一巡（不做内容打分）；醒点由上一次收尾 + 50–120 分钟随机间隔推出来（plan.py next）"
            % (len(hours()), GAP_MIN))


def main():
    ap = argparse.ArgumentParser(description="值班节奏：排班 + 该不该刷（plan.py）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gate", help="这一巡该不该刷（JSON）")
    sub.add_parser("rrule", help="打印排班 rrule（喂给 schedule_create）")
    sub.add_parser("hours", help="打印排班整点")
    sub.add_parser("next", help="算下一次醒点（锚点 + 随机间隔）并给一次性 rrule")
    a = ap.parse_args()

    if a.cmd == "gate":
        print(json.dumps(gate(), ensure_ascii=False, indent=2))
    elif a.cmd == "next":
        wake = next_wake()
        base = last_scan()
        print(json.dumps({
            "wake_at": wake.isoformat(),
            "from": base.isoformat() if base else None,
            "gap_min": int((wake - base).total_seconds() // 60) if base else None,
            "rrule": wake_rrule(wake),
        }, ensure_ascii=False, indent=2))
    elif a.cmd == "rrule":
        print(rrule())
    else:
        print(json.dumps({"hours": hours(), "plan": describe()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
