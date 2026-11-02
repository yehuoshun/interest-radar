#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_params.py —— 参数采用对账（A2 · 2026-11-02）。

只读审计：把 config.json 的「保存值」和真实运行证据（mention-log / write-log /
drafts / 当日日报）逐项对账，输出判定。对齐 SurfCore-Life 的证据哲学：
**保存 ≠ 采用，消费者的证据说了算。**

判定五档：
  ✅ adopted       实际证据与保存值一致（闸强制执行 / 模型按规则执行）
  ⏳ pending       暂无证据（不常触发 / 证据在微信侧等外部）
  ❌ conflict      实际 ≠ 保存值（模型没按 config 走 —— cron 告警位）
  ⚠️ drift         文档口径互斥（charter vs SKILL.md / config 与文本不等价）
  💤 not-consumed  代码零引用（死配置，改了不生效）

零网络、零写入。退出码：conflict>0 → 3（给 cron 告警），否则 0。
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta

from bili_radar.core import read_config, state_dir
from bili_radar.draft import load_drafts
from bili_radar.gates import _ago_h, mention_log, write_log

# ── 静态表：死配置（PARAMETERS.md 问题清单 3/4/5/6）─────────────────
NOT_CONSUMED = [
    ("mention.per_round", "代码闸只读 per_hour/per_day，per_round 从不入闸", "P#6"),
    ("mention.min_score", "全代码+tests 零引用；SKILL.md 只写「≥ min_score」不写数值，无人知道 17", "P#4"),
    ("mention.template", "comment.py 用硬编码兜底「@{name} 这个值得看一眼」", "P#5"),
]

# max_subtitles_per_round：B2（2026-11-02）已从 config 删除（老板 10-27 已拍板取消字幕上限）

# ── 静态表：文档口径互斥（PARAMETERS.md 问题清单 1/2）──
# 2026-11-02 老板拍板（AA）：#1 统一 10-27 口径（每轮 ≤1，charter 已同步）；
# #2 语义分层澄清（config max_push=@主号≤1，SKILL.md 0-3=汇报候选）→ 互斥解除，此表清空。
DRIFTS = []

# 日报留档条目的四维打分元组：（5/4/4/5）
SCORE_RE = re.compile(r"[（(](\d)\s*[/／]\s*(\d)\s*[/／]\s*(\d)\s*[/／]\s*(\d)\s*[)）]")


# ── 证据检查（每个返回一行 (param, saved, evidence, verdict)）───────
def _check_mentions(cfg, d):
    seg = cfg.get("mention") or {}
    per_hour = int(seg.get("per_hour", 1) if seg.get("per_hour") is not None else 1)
    per_day = int(seg.get("per_day") or 0)
    log = mention_log(d)
    if not log:
        return [("mention 频控", f"per_hour={per_hour} / per_day={per_day}",
                 "账本空（还没发过 @）", "pending")]
    out = []
    if per_hour > 0:
        n = sum(1 for r in log if _ago_h(r) < 1)
        out.append(("mention.per_hour", f"{per_hour} 条/小时", f"近 1h @ {n} 条",
                    "adopted" if n <= per_hour else "conflict"))
    if per_day > 0:
        n = sum(1 for r in log if _ago_h(r) < 24)
        out.append(("mention.per_day", f"{per_day} 条/天", f"近 24h @ {n} 条",
                    "adopted" if n <= per_day else "conflict"))
    return out


def _norm_ts(v):
    """统一为 naive：aware（如人工补录的 +08:00）转本地时区后剥离偏移，避免与 naive 混比。"""
    t = datetime.fromisoformat(str(v))
    if t.tzinfo is not None:
        t = t.astimezone().replace(tzinfo=None)
    return t


def _check_cooldown(cfg, d):
    min_gap = float((cfg.get("write") or {}).get("cooldown_sec", 120) or 120)
    # 只对账最近 7 天：写冷却 2026-10-27 才引入，更早的密集 @（10-15 每轮连发）是旧行为，不算今天的 conflict
    cutoff = datetime.now() - timedelta(days=7)
    recs = []
    for f in ("write-log.jsonl", "mention-log.jsonl"):
        p = d / f
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    if r.get("ts"):
                        t = _norm_ts(r["ts"])
                        if t >= cutoff:
                            recs.append(t)
                except Exception:  # noqa: BLE001 —— 同生产 _write_cooldown：坏行跳过
                    continue
    recs.sort()
    if not recs:
        return [("write.cooldown_sec", f"{min_gap:.0f}s", "无写记录", "pending")]
    gaps = [(recs[i + 1] - recs[i]).total_seconds() for i in range(len(recs) - 1)]
    bad = [g for g in gaps if 0 < g < min_gap]
    if bad:
        return [("write.cooldown_sec", f"{min_gap:.0f}s",
                 f"发现 {len(bad)} 次相邻写间隔 {min(bad):.0f}s < 上限", "conflict")]
    return [("write.cooldown_sec", f"{min_gap:.0f}s", f"{len(recs)} 条写记录全部满足", "adopted")]


def _check_write_kinds(cfg, d):
    out = []
    segs = cfg.get("write") or {}
    log = write_log(d)
    for kind in ("dynamic", "message", "comment"):
        seg = segs.get(kind) or {}
        if not seg.get("enabled"):
            continue
        ph, pd = int(seg.get("per_hour") or 0), int(seg.get("per_day") or 0)
        recs = [r for r in log if r.get("kind") == kind]
        if not recs:
            out.append((f"write.{kind} 频控", f"h≤{ph or '∞'} / d≤{pd or '∞'}",
                        "该 kind 无写记录", "pending"))
            continue
        if ph > 0:
            n = sum(1 for r in recs if _ago_h(r) < 1)
            out.append((f"write.{kind}.per_hour", str(ph), f"近 1h {n} 条",
                        "adopted" if n <= ph else "conflict"))
        if pd > 0:
            n = sum(1 for r in recs if _ago_h(r) < 24)
            out.append((f"write.{kind}.per_day", str(pd), f"近 24h {n} 条",
                        "adopted" if n <= pd else "conflict"))
    return out


def _draft_age_h(rec):
    """draft 记录用 sent_at/created_at 存时间（不是 ts），单独算距今小时数。"""
    try:
        t = datetime.fromisoformat(str(rec.get("sent_at") or rec.get("created_at")))
        return (datetime.now() - t).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        return 1e9


def _check_draft(cfg):
    seg = cfg.get("draft") or {}
    if not seg.get("enabled"):
        return []
    p12 = int(seg.get("per_12h", 1) or 1)
    p24 = int(seg.get("per_24h", 2) or 2)
    sent = [r for r in load_drafts() if r.get("status") == "sent"]
    if not sent:
        return [("draft 频控", f"12h≤{p12} / 24h≤{p24}", "无已批草稿", "pending")]
    n12 = sum(1 for r in sent if _draft_age_h(r) < 12)
    n24 = sum(1 for r in sent if _draft_age_h(r) < 24)
    cut = "adopted" if n24 <= p24 else "conflict"
    return [("draft 频控", f"12h≤{p12} / 24h≤{p24}",
             f"近 12h 已批 {n12} 条 / 近 24h {n24} 条", cut)]


def _check_report_score(cfg, d):
    saved = int((cfg.get("budget") or {}).get("min_total_score", 14) or 14)
    today = datetime.now().strftime("%Y-%m-%d")
    f = d / "out" / f"{today}.md"
    if not f.exists():
        return [("budget.min_total_score",
                 f"{saved}（B2 硬闸：comment --score < 它会被 code 拒）",
                 "今天还没有日报", "pending")]
    scores = []
    for line in f.read_text(encoding="utf-8").splitlines():
        for m in SCORE_RE.finditer(line):
            scores.append(sum(map(int, m.groups())))
    if not scores:
        return [("budget.min_total_score",
                 f"{saved}（B2 硬闸：comment --score < 它会被 code 拒）",
                 "日报里没解析到打分元组", "pending")]
    mn = min(scores)
    return [("budget.min_total_score",
             f"{saved}（B2 硬闸：comment --score < 它会被 code 拒）",
             f"日报 {len(scores)} 条留档最低分 {mn}",
             "adopted" if mn >= saved else "conflict")]


def _check_push(cfg):
    """max_push_per_round：10-27 语义 = @ 主号每轮 ≤1，已文本化进 SKILL.md:131 频控。

    代码侧 @ 闸读的是 mention.per_hour（config 里 max_push 零引用）→ 本质是
    文档镜像（与 min_total_score 同族）：config 与文档一致（都 1），但本地无
    「推送账本」可自证 → pending（诚实：无法动态核对）。
    """
    saved = int((cfg.get("budget") or {}).get("max_push_per_round", 1) or 0)
    return [("budget.max_push_per_round",
             f"{saved}（📐 文档镜像：@ 主号每轮 ≤1 已文本化进 SKILL.md:131 频控）",
             "config 与文档一致（10-27 口径）；本地无推送账本可自证，pending 不硬判",
             "pending")]


def _collect_static(cfg):
    out = []
    for path, why, ref in NOT_CONSUMED:
        top, _, sub = path.partition(".")
        if (cfg.get(top) or {}).get(sub) is not None:
            out.append((path, "（存在）", f"not-consumed：{why}（{ref}）", "not-consumed"))
    for path, why in DRIFTS:
        out.append((path, "（文档口径）", f"drift:{why}", "drift"))
    return out


# ── 汇总与输出 ───────────────────────────────────────────────────
def _rows(cfg, d):
    rows = []
    rows += _check_mentions(cfg, d)
    rows += _check_cooldown(cfg, d)
    rows += _check_write_kinds(cfg, d)
    rows += _check_draft(cfg)
    rows += _check_report_score(cfg, d)
    rows += _check_push(cfg)
    rows += _collect_static(cfg)
    return rows


def cmd_verify_params(a):
    """verify-params —— 参数采用对账（只读）。conflict>0 → exit 3。"""
    cfg = read_config()
    d = state_dir()
    rows = _rows(cfg, d)
    counts = Counter(v for _, _, _, v in rows)

    if a.json:
        print(json.dumps({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "summary": dict(counts),
            "conflict_exit": 3 if counts["conflict"] else 0,
            "rows": [{"param": p, "saved": s, "evidence": e, "verdict": v}
                     for p, s, e, v in rows],
        }, ensure_ascii=False, indent=2))
        sys.exit(3 if counts["conflict"] else 0)

    order = ["adopted", "pending", "conflict", "drift", "not-consumed"]
    mark = {"adopted": "✅", "pending": "⏳", "conflict": "❌",
            "drift": "⚠️", "not-consumed": "💤"}
    print(f"参数采用对账 · {datetime.now():%Y-%m-%d %H:%M} ｜ 保存值 vs 运行证据（只读）")
    print(f"{'=' * 48}")
    for v in order:
        for p, s, e, vv in rows:
            if vv != v:
                continue
            print(f"{mark[v]}[{v}] {p} = {s}")
            print(f"       实际：{e}")
    print("-" * 48)
    print(f"✅ adopted {counts['adopted']} · ⏳ pending {counts['pending']}"
          f" · ❌ conflict {counts['conflict']}"
          f" · ⚠️ drift {counts['drift']} · 💤 not-consumed {counts['not-consumed']}")
    if counts["conflict"]:
        print("⚠️ 存在 conflict：模型行为与保存值不符 —— 建议先看日报再查 PARAMETERS.md")
    elif counts["drift"] or counts["not-consumed"]:
        print("ℹ️ drift/not-consumed 是已知文档问题（PARAMETERS.md 问题清单），不影响今日采用判断")
    sys.exit(3 if counts["conflict"] else 0)