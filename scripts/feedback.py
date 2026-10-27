#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""feedback.py —— 反馈与活跃度域：反馈记账（weights/evidence）/ 统计 / 活跃度评估。"""
import json
import re
import time
from datetime import datetime, timedelta

from core import state_dir


def cmd_feedback(a):
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    wf = d / "weights.json"
    try:
        w = json.loads(wf.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        w = {"_note": "学习只来自 👍/👎 反馈 + 本人明写的兴趣线", "topics": {}}
    w.setdefault("topics", {})
    t = w["topics"].setdefault(a.topic, {"like": 0, "skip": 0, "weight": 0.0, "last": None})
    if a.signal in ("like", "skip"):
        t[a.signal] = int(t.get(a.signal, 0)) + 1
    # signal=note：只留证据，不动权重（例如"他只是问了一句"）
    n = t["like"] + t["skip"]
    t["weight"] = round(t["like"] / n, 3) if n else 0.0
    t["last"] = time.strftime("%Y-%m-%d")
    if a.note:
        t["last_note"] = a.note
    if a.score is not None:
        t["last_score"] = a.score
    w["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    wf.write_text(json.dumps(w, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (d / "evidence.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "topic": a.topic,
            "src": "bilibili" if a.bv else None, "id": a.bv,
            "signal": a.signal, "score": a.score, "note": a.note,
        }, ensure_ascii=False) + "\n")
    print(json.dumps({"topic": a.topic, **t}, ensure_ascii=False))


def cmd_stats(_a):
    d = state_dir()
    prof = d / "profile.md"
    topics = []
    if prof.exists():
        for line in prof.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*-\s*\[(\d)\]\s*(.+)$", line)
            if m:
                topics.append({"weight": int(m.group(1)), "line": m.group(2).strip()})
    try:
        w = json.loads((d / "weights.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        w = {"topics": {}}
    seen = 0
    sf = d / "seen.md"
    if sf.exists():
        seen = sum(1 for l in sf.read_text(encoding="utf-8").splitlines() if " | " in l)
    print(json.dumps({"profile_topics": topics, "weights": w.get("topics", {}),
                      "seen_count": seen, "updated": w.get("updated")},
                     ensure_ascii=False, indent=2))


def cmd_engagement(a):
    """活跃度评估（2026-10-27 老板校准：回复=兴趣高，不回复=兴趣不高；但故障≠信号）。

    汇总最近 N 天的信号供判读：
      老板反馈（evidence.jsonl 任意 signal） / 老板主动@（mention-log replied）
      老板批准草稿（drafts sent） / 雷达健康（out/ 报告日期数）
    verdict：故障（无报告产出，先查健康再谈信号）/ 活跃 / 纯沉默（建议试探性降频 + 先问本人）。
    """
    days = int(getattr(a, "days", 14) or 14)
    d = state_dir()
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    def in_window(ts):
        try:
            return datetime.fromisoformat(str(ts)) >= cutoff
        except Exception:  # noqa: BLE001
            return False

    feedback = 0
    ef = d / "evidence.jsonl"
    if ef.exists():
        for line in ef.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if in_window(r.get("ts")):
                    feedback += 1
            except Exception:  # noqa: BLE001
                pass

    owner_at = 0
    mf = d / "mention-log.jsonl"
    if mf.exists():
        for line in mf.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if in_window(r.get("ts")) and (r.get("kind") == "replied" or r.get("reply_to")):
                    owner_at += 1
            except Exception:  # noqa: BLE001
                pass

    drafts_ok = 0
    df = d / "drafts.jsonl"
    if df.exists():
        for line in df.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if r.get("status") == "sent" and in_window(r.get("sent_at") or r.get("created_at")):
                    drafts_ok += 1
            except Exception:  # noqa: BLE001
                pass

    reports = 0
    od = d / "out"
    if od.is_dir():
        for f in od.iterdir():
            if f.suffix == ".md":
                try:
                    if datetime.strptime(f.stem, "%Y-%m-%d") >= cutoff:
                        reports += 1
                except Exception:  # noqa: BLE001
                    pass

    active = feedback + owner_at + drafts_ok
    if reports == 0:
        verdict = "故障：最近无报告产出（先查 cookie/调度/推送，不降频）"
    elif active > 0:
        verdict = f"活跃（强信号 {active} 条，维持当前推送频率）"
    else:
        verdict = (f"纯沉默 {days} 天（0 反馈 0 互动）：建议试探性降频（3→1 条/周）"
                   f"且推送里先问本人『要不要少推点』；有反馈立即恢复")
    print(json.dumps({"days": days, "报告数": reports, "老板反馈": feedback,
                      "老板主动@": owner_at, "老板批准草稿": drafts_ok,
                      "活跃信号合计": active, "verdict": verdict},
                     ensure_ascii=False, indent=2))