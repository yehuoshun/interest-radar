#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schedule.py —— 兴趣雷达的调度模式（DSH 版，取代原来的 OpenClaw `apply-cron.py`）。

DSH 里没有 `openclaw cron`：定时任务由 agent 用 `schedule_create` 工具建，参数是
RFC 5545 子集（DTSTART + RRULE）+ 一段 prompt。所以本脚本不再改 cron，只负责：

  1. 按模式打印**现成的 rrule**（直接喂给 schedule_create）
  2. 打印**现成的 prompt**（templates/schedule-prompt.md 的内容）
  3. 把当前模式记进 state/config.json 的 schedule 段，供报告引用

用法：
    python scripts/schedule.py                # 看当前模式 + rrule + prompt
    python scripts/schedule.py all            # 全天每小时
    python scripts/schedule.py valley         # 梁文谷：只在 DeepSeek 谷时的小时跑
    python scripts/schedule.py all --minute 17 --rrule-only
    python scripts/schedule.py --prompt        # 只打印 prompt（不给模式就看当前模式）

谷时口径（DeepSeek 官方定价，2026-10 口径）：
    工作日 9:00–12:00、14:00–18:00 = **高峰**，其余（含整个周末）= **谷时**
    ⇒ 谷时的小时：0-8、12-13、18-23（保守写法：周末也会跳过 9-11/14-17，
      那两个窗口周末其实便宜 —— 想榨干可以再给周末单开一个任务）

整点请求太机器化：`--minute` 默认 17（每小时第 17 分钟触发），换个数字就是换个偏移。
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bili_radar.core import REPO_ROOT, read_config, state_dir  # noqa: E402

# 用固定 UTC+8，不用 zoneinfo：Windows 自带没有 IANA tzdata（会报 No module named 'tzdata'），
# 而中国自 1991 年起没有夏令时，UTC+8 就是 Asia/Shanghai。
TZ = timezone(timedelta(hours=8))
HOURS = {
    "all": list(range(24)),
    "valley": [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 18, 19, 20, 21, 22, 23],
}
DESC = {
    "all": "全天每小时逛一轮 B站",
    "valley": "梁文谷模式：只在 DeepSeek 谷时的小时（0-8/12-13/18-23）逛一轮",
}


def next_start(hours, minute) -> datetime:
    """DTSTART：现在之后最近一个「允许的小时 + 指定分钟」。"""
    now = datetime.now(TZ).replace(second=0, microsecond=0)
    for step in range(0, 48):
        cand = (now + timedelta(hours=step)).replace(minute=minute)
        if cand > now and cand.hour in hours:
            return cand
    return now.replace(hour=hours[0], minute=minute) + timedelta(days=1)


def build_rrule(mode: str, minute: int = 17) -> str:
    hours = HOURS[mode]
    start = next_start(hours, minute)
    byhour = ",".join(str(h) for h in hours)
    return (f"DTSTART;TZID=Asia/Shanghai:{start:%Y%m%dT%H%M%S}\n"
            f"RRULE:FREQ=DAILY;BYHOUR={byhour};BYMINUTE={minute}")


def prompt_text() -> str:
    f = REPO_ROOT / "templates" / "schedule-prompt.md"
    if f.is_file():
        return f.read_text(encoding="utf-8").strip()
    return "跑一轮兴趣雷达，按 code/interest-radar/SKILL.md 的一轮流程执行；正常静默。"


def save_state(mode: str, rrule: str) -> Path:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    cf = d / "config.json"
    try:
        cfg = json.loads(cf.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cfg = {}
    cfg["schedule"] = {
        "mode": mode,
        "rrule": rrule,
        "created_by": "scripts/schedule.py",
        "note": "谷时口径：工作日 9-12/14-18 高峰，其余含周末为谷时；DSH 用 schedule_create 建任务",
    }
    cf.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cf


def main():
    ap = argparse.ArgumentParser(description="兴趣雷达调度模式（DSH）：打印 rrule / prompt")
    ap.add_argument("mode", nargs="?", choices=sorted(HOURS), help="all | valley（省略=看当前）")
    ap.add_argument("--minute", type=int, default=17, help="每小时第几分钟触发（默认 17，避开整点）")
    ap.add_argument("--prompt", action="store_true", help="只打印 prompt")
    ap.add_argument("--rrule-only", action="store_true", help="只打印 rrule")
    a = ap.parse_args()

    cur = (read_config().get("schedule") or {}).get("mode") or "all"
    mode = a.mode or cur
    rrule = build_rrule(mode, a.minute)
    if mode != cur:
        save_state(mode, rrule)

    if a.prompt:
        print(prompt_text())
        return

    print(f"模式：**{mode}** —— {DESC[mode]}")
    print(f"rrule（喂给 schedule_create）：\n{rrule}")
    if not a.rrule_only:
        print("\nprompt：\n" + prompt_text())
        print("\n建任务时：target=this_session（提醒式）或 new_once（独立报告）；"
              "标题用「兴趣雷达 · 跑一轮」。")


if __name__ == "__main__":
    main()
