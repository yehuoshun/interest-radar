#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gates.py —— 写操作闸：写冷却 / 频控 / 失败自动关闸 / 账本。

依赖 core（state_dir/read_config/die）。comment/draft/notify/dynamic 的真发路径
必须过这里的闸（干跑不触发；删除类操作不冷却）。
"""
import json
import time
from datetime import datetime

from radar_lib.core import die, read_config, state_dir


def note_failure(d) -> int:
    """记一次发评论失败，返回今天的累计失败次数（≥3 → 调用方关闸）。"""
    f = d / "mention-fails.json"
    today = time.strftime("%Y-%m-%d")
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {}
    if data.get("date") != today:
        data = {"date": today, "count": 0}
    data["count"] = int(data.get("count", 0)) + 1
    try:
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return data["count"]


def write_log(d):
    """读写操作日志（write-log.jsonl，带 kind/时间戳），频控靠它。"""
    out = []
    f = d / "write-log.jsonl"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


def _write_cooldown(d, min_gap: float = 120.0):
    """写冷却（2026-10-27 对齐 whale）：距上一次写操作（评论/动态/私信/@）不足 min_gap 秒 → die。

    只查真发（账本里记的 ts 都是发出去的）；干跑不算。删除类（dynamic-del）不冷却（纠错优先）。
    """
    last = None
    for f in (d / "write-log.jsonl", d / "mention-log.jsonl"):
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                ts = r.get("ts")
                if ts:
                    t = datetime.fromisoformat(str(ts))
                    last = t if last is None or t > last else last
            except Exception:  # noqa: BLE001
                pass
    if last is not None:
        gap = (datetime.now() - last).total_seconds()
        if gap < min_gap:
            die(f"写冷却：距上一次写仅 {gap:.0f}s（要求 ≥ {min_gap:.0f}s）—— 防连击，稍后再发", 12)


def _write_gate(kind: str, rate: bool = True) -> dict:
    """通用写闸：① 该 kind 的 enabled 必须 true；② 频控（per_hour/per_day，按 kind 各算）。

    返回 config.write[kind] 那一段（调用方还要做正文/白名单/敏感词校验）。
    rate=False 用于「删除类」操作（删不该被发帖频控拦住）。
    """
    seg = ((read_config().get("write") or {}).get(kind) or {})
    if not seg.get("enabled"):
        die(f"闸①：config.json 的 write.{kind}.enabled 不是 true —— 拒绝发送", 4)
    if not rate:
        return seg
    d = state_dir()
    log = [r for r in write_log(d) if r.get("kind") == kind]
    per_hour = int(seg.get("per_hour") or 0)
    per_day = int(seg.get("per_day") or 0)
    if per_hour > 0 and sum(1 for r in log if _ago_h(r) < 1) >= per_hour:
        die(f"闸⑤：{kind} 最近 1 小时已发够（上限 {per_hour}/小时）—— 稍后再来", 11)
    if per_day > 0 and sum(1 for r in log if _ago_h(r) < 24) >= per_day:
        die(f"闸⑤：{kind} 最近 24 小时已发够（上限 {per_day}/天）—— 不再发", 11)
    return seg


def _write_fail(d, kind: str) -> int:
    """记一次写失败，返回今日累计；连续 3 次 → 自动关掉该 kind 的开关（防账号被爆）。"""
    f = d / f"write-fails-{kind}.json"
    today = time.strftime("%Y-%m-%d")
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {}
    if data.get("date") != today:
        data = {"date": today, "count": 0}
    data["count"] = int(data.get("count", 0)) + 1
    try:
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    if data["count"] >= 3:
        cf = d / "config.json"
        try:
            cfgall = json.loads(cf.read_text(encoding="utf-8"))
            cfgall.setdefault("write", {}).setdefault(kind, {})["enabled"] = False
            cf.write_text(json.dumps(cfgall, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"⚠️ {kind} 连续 3 次失败 → 已自动关掉 write.{kind}.enabled（防账号被爆），等本人来看",
                  file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
    return data["count"]


def _record_write(d, rec: dict):
    with (d / "write-log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def mention_log(d):
    """读 mentions 发出记录（带时间戳）。"""
    out = []
    f = d / "mention-log.jsonl"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


def _ago_h(rec):
    try:
        return (datetime.now() - datetime.fromisoformat(str(rec.get("ts")))).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        return 1e9