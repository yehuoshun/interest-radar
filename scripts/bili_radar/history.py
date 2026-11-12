#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""history.py —— 参数变更账本（A4 · 2026-11-02）。

state_dir()/param-history.jsonl：给 config 变更加「来路」——对齐 SurfCore-Life
life_history 的精华：**谁改的、为什么改、改前改后、事后观察、与回滚的关系**。
铁律：reason 只记人（老板/我）明说的理由，程序不编造。

事件行（JSONL 纯追加，历史不可变）：
- kind=change    参数变更        param/before/after/actor/reason
- kind=rollback  配置整体回滚    rollback_to=<备份名> / changed=<实际变动的参数列表>
- kind=observe   事后观察        change_id=<关联的 change id> / note

零网络；除追加账本行外零副作用。
"""
import json
import sys
import time
import uuid
from datetime import datetime

from bili_radar.core import die, state_dir


def hist_file(d):
    return d / "param-history.jsonl"


def _nid(kind: str) -> str:
    return f"{kind}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def append_change(d, *, actor: str, param: str, before, after, reason=None,
                   approved_by=None):
    """记一次参数变更（set / rate / approve 真写后调用）。actor: boss|agent|auto。

    approved_by：敏感项直改时的老板批准留痕（原话或 approve 的申请 id）。
    """
    rec = {"kind": "change", "id": _nid("chg"), "ts": _ts(), "actor": actor,
           "param": param, "before": before, "after": after,
           "reason": reason, "approved_by": approved_by, "rollback_to": None,
           "changed": None}
    with hist_file(d).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec["id"]


def append_rollback(d, *, backup_name: str, changed):
    """记一次整体配置回滚（config restore 真写后调用）。changed=[(param, before, after), ...]。"""
    rec = {"kind": "rollback", "id": _nid("rbk"), "ts": _ts(), "actor": "agent",
           "param": "*", "before": None, "after": None, "reason": None,
           "rollback_to": backup_name, "changed": changed}
    with hist_file(d).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec["id"]


def append_observe(d, *, change_id: str, note: str):
    """记一次事后观察（life_observe 的轻量版）：本人/我报告「这个改动后来效果如何」。"""
    rec = {"kind": "observe", "id": _nid("obs"), "ts": _ts(), "actor": "agent",
           "param": None, "before": None, "after": None, "reason": None,
           "rollback_to": None, "changed": None,
           "change_id": change_id, "note": note}
    with hist_file(d).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec["id"]


def load_history(d):
    f = hist_file(d)
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def diff_params(old_cfg, new_cfg, prefix=""):
    """递归 diff 两版 config，返回实际变动的 [[param, before, after], ...]（仅标量）。"""
    out = []
    keys = set(old_cfg) | set(new_cfg)
    for k in sorted(keys):
        p = f"{prefix}.{k}" if prefix else k
        va, vb = old_cfg.get(k, "<absent>"), new_cfg.get(k, "<absent>")
        if isinstance(va, dict) and isinstance(vb, dict):
            out += diff_params(va, vb, p)
        elif va != vb:
            out.append([p, va, vb])
    return out


def _fmt(v):
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def cmd_cfg_log(a):
    """config log [--param X] [--json] —— 打印参数变更时间线（A4）。"""
    rows = load_history(state_dir())
    if a.param:
        keep_chg = {r["id"] for r in rows
                    if r.get("kind") == "change" and r.get("param") == a.param}
        rows = [r for r in rows
                if (r.get("kind") == "change" and r["id"] in keep_chg)
                or (r.get("kind") == "rollback" and a.param in
                    [c[0] for c in (r.get("changed") or [])])
                or (r.get("kind") == "observe" and r.get("change_id") in keep_chg)]
    rows.sort(key=lambda r: r.get("ts", ""))

    if a.json:
        print(json.dumps({"count": len(rows), "rows": rows},
                          ensure_ascii=False, indent=2))
        return

    if not rows:
        print("参数变更账本为空（还没人改过参数）—— 用 config set/restore 会在这里留痕")
        return
    print(f"参数变更账本 · {len(rows)} 条（state_dir()/param-history.jsonl）\n")
    for r in rows:
        ts = r.get("ts", "?")[:16]
        if r.get("kind") == "change":
            print(f"[{ts}] CHG {r['id']}  {r.get('param')}: "
                  f"{_fmt(r.get('before'))} → {_fmt(r.get('after'))}  by {r.get('actor')}")
            if r.get("reason"):
                print(f"         理由：{r['reason']}")
            if r.get("approved_by"):
                print(f"         批准：{r['approved_by']}")
        elif r.get("kind") == "rollback":
            print(f"[{ts}] 回滚 {r['id']}  整份配置 → 备份 {r.get('rollback_to')}")
            for p, b, af in (r.get("changed") or [])[:8]:
                print(f"         {p}: {_fmt(b)} → {_fmt(af)}")
            if len(r.get("changed") or []) > 8:
                print(f"         …另有 {len(r['changed']) - 8} 个参数")
        else:  # observe
            print(f"[{ts}] 观察 {r['id']}  → {r.get('change_id')}: {r.get('note')}")


def cmd_cfg_observe(a):
    """config observe <change_id> --note "..." —— 给某次变更补一条事后观察。"""
    rows = load_history(state_dir())
    if not any(r.get("id") == a.change_id and r.get("kind") == "change"
               for r in rows):
        die(f"找不到变更 {a.change_id}（用 config log 看有哪些）")
    oid = append_observe(state_dir(), change_id=a.change_id, note=a.note)
    print(f"✅ 已记录观察 {oid} → {a.change_id}")