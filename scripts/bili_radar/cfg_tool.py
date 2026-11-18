#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cfg_tool.py —— 配置修改工具（A3 · 2026-11-02，B1 审批闸 · 2026-11-02）。

radar.py config set / restore / list：给 config.json 的人工修改套上
「干跑 → 备份 → 确认写入 → 可回滚」的安全网（对齐 SurfCore-Life 的
「备份失败拒提交 + 回滚保护」）。

- set     默认干跑（只打印 before → after）；--yes 才写；写前自动备份
          （gates.backup_config，保留最近 10 份）；写后重读校验
- restore 列出/恢复备份；恢复前把当前 config 再备份一份（反悔可回），
          并提示「备份后又改过」的期间改动
- 敏感项（开关/白名单/频控）与已知死配置/漂移（PARAMETERS.md 问题清单）显式提醒

B1 审批闸（2026-11-02）：SENSITIVE 集合内的参数 = 必须老板批准才能直改：
- 快速：config set --yes --approved-by "老板原话"（批准留痕账本）
- 正规：config propose → 老板点头 → config approve / reject
- 批准后的写入走同一套：备份 → 原子写 → 写后校验 → 入账本（actor=boss）

零网络；除 --yes / approve 写入外零副作用。
"""
import json
import sys
import time
import uuid
from datetime import datetime

from bili_radar.core import die, read_config, state_dir
from bili_radar.gates import atomic_write_config, backup_config

# B1（2026-11-02）：敏感项 = 必须老板批准才允许 set --yes 直改（否则只能走 propose）
SENSITIVE = {
    # @ 目标与 @ 闸
    "mention.enabled", "mention.mid", "mention.forbid",
    "mention.per_round", "mention.per_hour", "mention.per_day",
    # 写操作闸（dynamic / message / comment + 总冷却）
    "write.cooldown_sec",
    "write.dynamic.enabled", "write.dynamic.per_hour", "write.dynamic.per_day",
    "write.dynamic.forbid",
    "write.message.enabled", "write.message.per_hour", "write.message.per_day",
    "write.message.forbid", "write.message.allow_mid",
    "write.comment.enabled", "write.comment.per_hour", "write.comment.per_day",
    "write.comment.forbid", "write.comment.same_video_once",
    # 点赞闸（2026-11-13 新增）
    "write.like.enabled", "write.like.per_hour", "write.like.per_day",
    "write.like.same_video_once",
    # 草稿审批流
    "draft.enabled", "draft.per_12h", "draft.per_24h", "draft.forbid",
    "draft.reply_interval_days",
    # B2 硬闸阈值（2026-11-18 补）：谁都能改就等于没有闸 —— 改它必须留老板批准
    "budget.min_total_score",
}

PROPOSALS_FILE = "proposals.json"

# 已知死配置 / 漂移（与 PARAMETERS.md 问题清单同步；set 时直接提示）
KNOWN_NOTES = [
    (("mention", "per_round"), "💤 死配置：代码闸只读 per_hour/per_day，这个值改了不生效（PARAMETERS.md #6）"),
    (("mention", "min_score"), "💤 死配置：没有任何执行者知道这个值（PARAMETERS.md #4）"),
    (("mention", "template"), "💤 死配置：comment.py 用硬编码兜底文案（PARAMETERS.md #5）"),
    (("budget", "min_total_score"), "✅ B2 硬闸阈值（2026-11-02 转正；11-18 起属敏感项）：comment --score < 它会被 code 拒发"),
    (("budget", "max_push_per_round"), "⚠️ 漂移：SKILL.md 仍写「只推 0-3 条」，模型看到的真值是 0-3（PARAMETERS.md #2）"),
]
# 特别提示：闸⑥实际生效的是 per_hour（rate 快捷面板也在改它）
IMMEDIATE_EFFECT = {
    "mention.per_hour": "这是闸⑥实际生效项（每轮 ≤1 目前靠它兜底）；per_round 不参与闸判断",
}


def _parse_value(raw: str):
    """值解析：先试 JSON（数字/bool/列表/字典），失败按字符串。"""
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _navigate(cfg, parts):
    """沿点分路径导航；找不到就 die。返回 (node, key)。"""
    node = cfg
    for p in parts[:-1]:
        if not isinstance(node, dict) or p not in node:
            have = ", ".join(sorted(node)) if isinstance(node, dict) else "（不是对象）"
            die(f"config.json 里没有 {'.'.join(parts)}（停在 {p}；现有：{have}）")
        node = node[p]
    key = parts[-1]
    if not isinstance(node, dict) or key not in node:
        have = ", ".join(sorted(node)) if isinstance(node, dict) else "（不是对象）"
        die(f"config.json 里没有 {'.'.join(parts)}（现有键：{have}）")
    return node, key


def _apply_batch(d, items, *, actor, reason=None, approved_by=None):
    """一次真写多项：备份 → 原子写 → 写后校验 → 逐项入账本（set / approve / set-many 共用）。

    items: [(parts, new_val), ...]（调用方已校验过路径与值）。
    **只备份一次**：一个意图改多项时不把撤销槽吃光（11-14 那批 9 条命令占了 9 份）。
    写入整体原子：任何一步失败都 die，备份里是可一键 restore 的旧值。
    返回 (bak, [change_id, ...])。
    """
    cf = d / "config.json"
    bak = backup_config(d)
    if bak is None:
        die("备份 config.json 失败 —— 拒绝写入（备份失败不提交）")
    befores = {}

    def mutate(cfg2):
        for i, (parts, new_val) in enumerate(items):
            nd = cfg2
            for p2 in parts[:-1]:
                nd = nd[p2]
            befores[i] = nd[parts[-1]]
            nd[parts[-1]] = new_val
        return cfg2

    atomic_write_config(d, mutate)
    # 写后重读校验：JSON 可解析 + 每项都能按原路径读回新值
    try:
        chk = json.loads(cf.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        die(f"写后校验失败：{e} —— 请 config restore {bak.name}")
    for parts, new_val in items:
        cur = chk
        for p in parts[:-1]:
            cur = (cur or {}).get(p)
        if not isinstance(cur, dict) or cur.get(parts[-1]) != new_val:
            die(f"写后校验失败：{'.'.join(parts)} 读不回 —— 配置可能损坏，请 config restore {bak.name}")
    from bili_radar.history import append_change
    cids = []
    for i, (parts, new_val) in enumerate(items):
        cids.append(append_change(d, actor=actor, param=".".join(parts),
                                  before=befores.get(i), after=new_val,
                                  reason=reason, approved_by=approved_by))
    return bak, cids


def _apply_set(d, parts, new_val, *, actor, reason=None, approved_by=None):
    """执行一次真写（= 单项批次）：备份 → 原子写 → 写后校验 → 入账本。

    返回 (bak, change_id)。任何一步失败都 die（备份失败拒提交、校验失败提示还原）。
    """
    bak, cids = _apply_batch(d, [(parts, new_val)], actor=actor,
                             reason=reason, approved_by=approved_by)
    return bak, cids[0]


def _find_backups(d):
    out = []
    for p in sorted(d.glob("config.json.bak-*")):
        st = p.stat()
        out.append({"name": p.name, "mtime": datetime.fromtimestamp(st.st_mtime),
                    "size": st.st_size})
    return out


def cmd_cfg_set(a):
    """config set <path> <value> [--yes] —— 干跑默认，--yes 才写；写前备份；写后入账本。"""
    d = state_dir()
    cf = d / "config.json"
    if not cf.exists():
        die(f"没有 config.json：{cf}")

    parts = a.path.split(".")
    if not (2 <= len(parts) <= 3):
        die(f"路径应为 2-3 层 <段>.<键> 或 <段>.<子段>.<键>，如 mention.per_hour / write.message.allow_mid（得到：{a.path}）")

    cfg = read_config()
    node, key = _navigate(cfg, parts)
    old_val = node[key]
    new_val = _parse_value(a.value)
    if new_val == old_val:
        print(f"{a.path} 已是 {old_val!r}，无需修改 · 干跑结束")
        return

    for (t, k), note in KNOWN_NOTES:
        if t == parts[0] and k == key:
            print(note)
    if a.path in SENSITIVE:
        print(f"🔒 敏感项：{a.path} 涉及账号安全或闸门行为 —— 真写需要老板批准")
    if a.path in IMMEDIATE_EFFECT:
        print(f"ℹ️ {IMMEDIATE_EFFECT[a.path]}")

    print(f"💡 干跑：{a.path}：{old_val!r} → {new_val!r}")
    print("     写入前会自动备份 config.json（保留最近 10 份），事后可用 config restore 还原")
    if not a.yes:
        print("（干跑：要真写请加 --yes）", file=sys.stderr)
        return

    # B1 审批闸：敏感项直改必须带老板批准（留痕账本），否则只能走 propose/approve
    approved_by = getattr(a, "approved_by", None)
    if a.path in SENSITIVE and not approved_by:
        die(f"🔒 {a.path} 是敏感项 —— 必须老板批准才能直改：\n"
            f"   ① 快速：加 --approved-by \"老板原话\"（批准留痕入账本）\n"
            f"   ② 正规：config propose {a.path} {a.value} [--reason …] → 老板点头 → config approve <id>")
    if approved_by:
        print(f"🔒 敏感项批准已留痕：{approved_by}")

    bak, cid = _apply_set(d, parts, new_val, actor=getattr(a, "actor", "agent"),
                          reason=getattr(a, "reason", None),
                          approved_by=approved_by)
    print(f"✅ 已写入 {a.path} = {new_val!r}（备份：{bak.name}；账本：{cid}）")


def _parse_many_items(raw_items):
    """解析 ["段.键=值", ...] → [(parts, new_val, old_val, path)]，并挡重复路径。

    只解析、不写；路径不存在或格式不对立刻 die（干跑阶段就把错挑出来）。
    """
    cfg = read_config()
    out, seen = [], set()
    for raw in raw_items:
        if "=" not in raw:
            die(f"格式应为 <段.键>=<值>（得到：{raw!r}）")
        path, val_raw = raw.split("=", 1)
        path = path.strip()
        parts = path.split(".")
        if not (2 <= len(parts) <= 3):
            die(f"路径应为 2-3 层 <段>.<键>，如 mention.per_hour（得到：{path}）")
        if path in seen:
            die(f"同一批里 {path} 出现两次 —— 一次只改一个值，别让谁覆盖谁看不出来")
        seen.add(path)
        node, key = _navigate(cfg, parts)
        out.append((parts, _parse_value(val_raw), node[key], path))
    return out


def cmd_cfg_set_many(a):
    """config set-many <段.键=值> [<段.键=值> ...] [--yes] —— 一次备份、一次原子写、逐项入账。

    用于「一个意图改多项」：单条 config set 每条都备份，改 9 项就吃掉 9 个撤销槽
    （11-14 那次正是如此）。这里只备份 1 份，写入仍整体原子（全成或全不成）。
    """
    d = state_dir()
    cf = d / "config.json"
    if not cf.exists():
        die(f"没有 config.json：{cf}")

    parsed = _parse_many_items(a.items)
    todo, noop = [], []
    for (parts, new_val, old_val, path) in parsed:
        (noop if (type(new_val) is type(old_val) and new_val == old_val) else todo).append(
            (parts, new_val, old_val, path))

    for _p, _v, _o, path in noop:
        print(f"… {path} 值未变，跳过")
    for (parts, new_val, old_val, path) in todo:
        for (t, k), note in KNOWN_NOTES:
            if t == parts[0] and k == parts[-1]:
                print(note)
        if path in IMMEDIATE_EFFECT:
            print(f"ℹ️ {IMMEDIATE_EFFECT[path]}")
        print(f"💡 干跑：{path}：{old_val!r} → {new_val!r}")
    if not todo:
        print("全部无需修改 · 干跑结束")
        return

    sens = [path for (_p, _v, _o, path) in todo if path in SENSITIVE]
    if sens:
        print(f"🔒 敏感项 {len(sens)} 个：{', '.join(sens)} —— 真写需要老板批准")
    print(f"     共 {len(todo)} 项；写入前只备份一次 config.json（保留最近 10 份），"
          f"写错可用 config restore 一键还原")
    if not a.yes:
        print("（干跑：要真写请加 --yes）", file=sys.stderr)
        return

    approved_by = getattr(a, "approved_by", None)
    if sens and not approved_by:
        die("🔒 这批含敏感项 —— 必须老板批准才能直改：\n"
            f"   {', '.join(sens)}\n"
            "   加 --approved-by \"老板原话\"（批准留痕入账本）")
    if approved_by:
        print(f"🔒 敏感项批准已留痕：{approved_by}")

    bak, cids = _apply_batch(d, [(p, v) for (p, v, _o, _pa) in todo],
                             actor=getattr(a, "actor", "agent"),
                             reason=getattr(a, "reason", None),
                             approved_by=approved_by)
    ids = cids[0] if len(cids) == 1 else f"{cids[0]} … {cids[-1]}"
    print(f"✅ 已写入 {len(todo)} 项（备份：{bak.name}；账本 {len(cids)} 条：{ids}）")


def cmd_cfg_restore(a):
    """config restore [name] [--list] [--yes] —— 列出/恢复配置备份。"""
    d = state_dir()
    baks = _find_backups(d)

    if a.list or not a.name:
        if not baks:
            print("没有备份（config.json.bak-*）")
            return
        print(f"共 {len(baks)} 份备份（config restore <名称> --yes 恢复）：")
        for b in baks:
            print(f"  {b['name']}  {b['mtime']:%Y-%m-%d %H:%M:%S}  {b['size']}B")
        return

    target = d / a.name
    if not target.exists() or "config.json.bak-" not in target.name:
        die(f"备份不存在：{a.name}（用 config restore --list 查看）")

    cf = d / "config.json"
    bak_mt = datetime.fromtimestamp(target.stat().st_mtime)
    if not cf.exists():
        die(f"没有 config.json 可恢复（{cf} 不存在）")
    cur_mt = datetime.fromtimestamp(cf.stat().st_mtime)
    print(f"备份时间：{bak_mt:%Y-%m-%d %H:%M:%S}；当前 config 最后修改：{cur_mt:%Y-%m-%d %H:%M:%S}")
    if cur_mt > bak_mt:
        print(f"⚠️ 备份之后 config 又被改过 —— 恢复会覆盖后来的改动（期间内容将以新备份形式保留）")

    if not a.yes:
        print(f"💡 干跑：将用 {target.name} 覆盖 config.json")
        print("（要真恢复请加 --yes）", file=sys.stderr)
        return

    pre = backup_config(d)
    if pre is None:
        die("恢复前备份当前 config 失败 —— 拒绝恢复（保持现状不动）")

    # B3（2026-11-02）：原子替换 + 乐观锁（不用 copy2 直写，避免半截文件）
    def m(_cfg2):
        return json.loads(target.read_text(encoding="utf-8"))

    atomic_write_config(d, m)
    # A4：回滚入账本 —— changed = 恢复实际变动的参数（diff pre=恢复前 vs target=恢复后）
    from bili_radar.history import append_rollback, diff_params
    try:
        changed = diff_params(json.loads(pre.read_text(encoding="utf-8")),
                               json.loads(target.read_text(encoding="utf-8")))
        rid = append_rollback(d, backup_name=target.name, changed=changed)
        print(f"✅ 已恢复 {target.name} → config.json（恢复前状态在 {pre.name}；账本：{rid}）")
    except Exception as e:  # noqa: BLE001
        print(f"✅ 已恢复 {target.name} → config.json（恢复前状态在 {pre.name}）", file=sys.stderr)
        print(f"⚠️ 账本写入失败（{e}）—— 不影响恢复结果，可手动补记", file=sys.stderr)


# ── B1 审批闸（2026-11-02）────────────────────────────────────────

def _load_proposals(d):
    f = d / PROPOSALS_FILE
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:  # noqa: BLE001
        pass
    return []


def _save_proposals(d, items):
    (d / PROPOSALS_FILE).write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_cfg_propose(a):
    """config propose <path> <value> [--reason …] —— 提交变更申请（不写，等人批准）。"""
    d = state_dir()
    parts = a.path.split(".")
    if not (2 <= len(parts) <= 3):
        die(f"路径应为 2-3 层 <段>.<键> 或 <段>.<子段>.<键>（得到：{a.path}）")
    cfg = read_config()
    _navigate(cfg, parts)  # 校验路径现在还活着（die 就说明要重新申请）
    new_val = _parse_value(a.value)
    items = _load_proposals(d)
    for it in items:
        if it.get("status") == "pending" and it.get("path") == a.path:
            die(f"同参数已有待批申请 {it['id']}（{it['path']}={it['value']!r}）"
                f"—— 先 config approve/reject {it['id']}")
    pid = f"pln-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    items.append({
        "id": pid, "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "path": a.path, "value": new_val, "raw": a.value,
        "reason": getattr(a, "reason", None), "status": "pending",
        "decided_ts": None, "decided_note": None,
    })
    _save_proposals(d, items)
    tip = f"（理由：{a.reason}）" if getattr(a, "reason", None) else ""
    print(f"📨 已提交申请 {pid}：{a.path} = {new_val!r}{tip}")
    print(f"   等老板批准 → config approve {pid}")
    print(f"   不批       → config reject {pid} [--reason …]")


def cmd_cfg_approve(a):
    """config approve <申请id> —— 老板批准后真写（同样走备份+原子写+账本，actor=boss）。"""
    d = state_dir()
    items = _load_proposals(d)
    hit = next((it for it in items if it.get("id") == a.id), None)
    if hit is None:
        die(f"没有这个申请：{a.id}（config proposals 看全部）")
    if hit.get("status") != "pending":
        die(f"申请 {a.id} 已被 {hit.get('status')}（{hit.get('decided_ts')}），不能重复处理")
    parts = hit["path"].split(".")
    if not (2 <= len(parts) <= 3):
        die(f"申请路径异常（{hit['path']}）—— 拒绝执行，请先 reject 该申请")
    # 重新校验路径/值仍有效（批准前 config 可能已被别人改过）
    _navigate(read_config(), parts)
    bak, cid = _apply_set(d, parts, hit["value"], actor="boss",
                          reason=hit.get("reason"),
                          approved_by=f"config approve {hit['id']}")
    hit["status"] = "approved"
    hit["decided_ts"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    hit["decided_note"] = f"change={cid}, backup={bak.name}"
    _save_proposals(d, items)
    print(f"✅ 已批准并写入 {hit['path']} = {hit['value']!r}（账本：{cid}；备份：{bak.name}）")


def cmd_cfg_reject(a):
    """config reject <申请id> [--reason …] —— 驳回申请（不写 config）。"""
    d = state_dir()
    items = _load_proposals(d)
    hit = next((it for it in items if it.get("id") == a.id), None)
    if hit is None:
        die(f"没有这个申请：{a.id}（config proposals 看全部）")
    if hit.get("status") != "pending":
        die(f"申请 {a.id} 已被 {hit.get('status')}（{hit.get('decided_ts')}），不能重复处理")
    hit["status"] = "rejected"
    hit["decided_ts"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    hit["decided_note"] = getattr(a, "reason", None)
    _save_proposals(d, items)
    print(f"❌ 已驳回 {a.id}：{hit['path']} = {hit['value']!r}（未写入 config）")


def cmd_cfg_proposals(a):
    """config proposals [--all] [--json] —— 申请列表（默认只 pending；超 24h 标 stale）。"""
    d = state_dir()
    items = _load_proposals(d)
    if a.json:
        print(json.dumps({"count": len(items), "items": items},
                          ensure_ascii=False, indent=2))
        return
    if not items:
        print("没有变更申请（config propose 提交；config approve/reject 处理）")
        return
    now = datetime.now()
    shown = items if a.all else [it for it in items if it.get("status") == "pending"]
    if not shown:
        print("没有待批申请（config proposals --all 看历史）")
        return
    tag = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
    for it in shown:
        ts = str(it.get("ts", "?"))[:16]
        stale = ""
        try:
            t = datetime.strptime(it["ts"], "%Y-%m-%dT%H:%M:%S")
            if it.get("status") == "pending" and (now - t).total_seconds() > 24 * 3600:
                stale = " ⚠️ 已超 24h（stale，仍可批/驳）"
        except Exception:  # noqa: BLE001
            pass
        print(f"{tag.get(it['status'], '?')} {it['id']}  {ts}  {it['path']} = {it['value']!r}{stale}")
        if it.get("reason"):
            print(f"    理由：{it['reason']}")
        if it.get("status") != "pending" and it.get("decided_ts"):
            note = f"：{it['decided_note']}" if it.get("decided_note") else ""
            print(f"    {it['status']} 于 {str(it['decided_ts'])[:16]}{note}")