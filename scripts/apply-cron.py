#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply-cron.py —— 切换兴趣雷达的调度模式（**DeepSeek 专属配置**）

    python3 apply-cron.py            # 看当前模式
    python3 apply-cron.py all        # 全天每小时
    python3 apply-cron.py valley     # 梁文谷：只在 DeepSeek 谷时的小时跑

谷时口径（DeepSeek 官方定价，2026-10 口径）：
    工作日 9:00–12:00、14:00–18:00 = **高峰**，其余（含整个周末）= **谷时**
    ⇒ 谷时的小时：0-8、12-13、18-23（保守写法：周末也会跳过 9-11/14-17，
      那两个窗口周末其实便宜 —— 想榨干可以再给周末单开一个 job）

它只改 cron 的表达式，其它（会话、工具白名单、投递、异常告警）一律不动。
"""
import json
import subprocess
import sys
from pathlib import Path

EXPR = {
    "all": "0 * * * *",
    "valley": "0 0-8,12,13,18-23 * * *",
}
DESC = {
    "all": "全天每小时逛一轮 B站",
    "valley": "梁文谷模式：只在 DeepSeek 谷时的小时（0-8/12-13/18-23）逛一轮",
}
NAME = "兴趣雷达"


def state_dir() -> Path:
    p = Path(__file__).resolve().parents[3] / "interests"
    return p if p.exists() else Path.home() / ".openclaw" / "workspace" / "interests"


def find_job():
    f = Path.home() / ".openclaw" / "cron" / "jobs.json"
    if not f.exists():
        return None
    for j in json.loads(f.read_text(encoding="utf-8")).get("jobs", []):
        if str(j.get("name", "")).startswith(NAME):
            return j
    return None


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    job = find_job()
    if not job:
        print("ERROR: 没找到兴趣雷达的 cron 任务", file=sys.stderr)
        sys.exit(1)
    cur = (job.get("schedule") or {}).get("expr", "")
    now_mode = next((m for m, e in EXPR.items() if e == cur), f"其它({cur})")

    if mode not in EXPR:
        print(f"当前模式：**{now_mode}**（{cur}）\n可用：all | valley")
        return

    subprocess.run(["openclaw", "cron", "edit", job["id"],
                    "--cron", EXPR[mode], "--tz", "Asia/Shanghai",
                    "--description",
                    f"{DESC[mode]}：读主号在评论区的反馈 → 搜/粗筛/读字幕（≤3条）→ 打分判重 → "
                    f"追加报告 → 够格且今天没 @ 过才 @主号 1 条；正常静默，异常推微信"],
                   check=True, capture_output=True, text=True)
    # 记一笔，方便别的脚本/报告引用
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    cf = d / "config.json"
    try:
        cfg = json.loads(cf.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cfg = {}
    cfg["schedule"] = {"mode": mode, "cron": EXPR[mode],
                       "note": "谷时口径：工作日 9-12/14-18 高峰，其余含周末为谷时"}
    cf.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ 已切到 **{mode}**（{EXPR[mode]}）\n   {DESC[mode]}")


if __name__ == "__main__":
    main()
