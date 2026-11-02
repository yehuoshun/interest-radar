#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cfg_tool.py —— 配置修改工具（A3 · 2026-11-02）。

radar.py config set / restore / list：给 config.json 的人工修改套上
「干跑 → 备份 → 确认写入 → 可回滚」的安全网（对齐 SurfCore-Life 的
「备份失败拒提交 + 回滚保护」）。

- set     默认干跑（只打印 before → after）；--yes 才写；写前自动备份
          （gates.backup_config，保留最近 10 份）；写后重读校验
- restore 列出/恢复备份；恢复前把当前 config 再备份一份（反悔可回），
          并提示「备份后又改过」的期间改动
- 敏感项（开关/白名单/频控）与已知死配置/漂移（PARAMETERS.md 问题清单）显式提醒

零网络；除 --yes 写入外零副作用。
"""
import json
import sys
from datetime import datetime

from bili_radar.core import die, read_config, state_dir
from bili_radar.gates import atomic_write_config, backup_config

# 敏感项：改动涉及账号安全 / 闸门行为（提醒但不拦——维护者是老板）
SENSITIVE_KEYS = {"enabled", "allow_mid", "forbid", "per_hour", "per_day", "per_12h",
                  "per_24h", "cooldown_sec", "per_round", "min_score",
                  "min_total_score", "max_subtitles_per_round", "max_push_per_round"}

# 已知死配置 / 漂移（与 PARAMETERS.md 问题清单同步；set 时直接提示）
KNOWN_NOTES = [
    (("mention", "per_round"), "💤 死配置：代码闸只读 per_hour/per_day，这个值改了不生效（PARAMETERS.md #6）"),
    (("mention", "min_score"), "💤 死配置：没有任何执行者知道这个值（PARAMETERS.md #4）"),
    (("mention", "template"), "💤 死配置：comment.py 用硬编码兜底文案（PARAMETERS.md #5）"),
    (("budget", "max_subtitles_per_round"), "💤 死配置：代码零引用，改了不生效（PARAMETERS.md #3）"),
    (("budget", "min_total_score"), "📐 模型规则镜像：模型读的是 SKILL.md 文本（14），config 只是镜像（PARAMETERS.md #3）"),
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
    # 沿路径导航到父对象（2 层：cfg[top]；3 层：cfg[top][mid]）
    node = cfg
    for p in parts[:-1]:
        if not isinstance(node, dict) or p not in node:
            have = ", ".join(sorted(node)) if isinstance(node, dict) else "（不是对象）"
            die(f"config.json 里没有 {a.path}（停在 {p}；现有：{have}）")
        node = node[p]
    key = parts[-1]
    if not isinstance(node, dict) or key not in node:
        have = ", ".join(sorted(node)) if isinstance(node, dict) else "（不是对象）"
        die(f"config.json 里没有 {a.path}（现有键：{have}）")

    old_val = node[key]
    new_val = _parse_value(a.value)
    if new_val == old_val:
        print(f"{a.path} 已是 {old_val!r}，无需修改 · 干跑结束")
        return

    for (t, k), note in KNOWN_NOTES:
        if t == parts[0] and k == key:
            print(note)
    if key in SENSITIVE_KEYS:
        print(f"🔒 敏感项：{a.path} 涉及账号安全或闸门行为 —— 请确认这是你想要的")
    if a.path in IMMEDIATE_EFFECT:
        print(f"ℹ️ {IMMEDIATE_EFFECT[a.path]}")

    print(f"💡 干跑：{a.path}：{old_val!r} → {new_val!r}")
    print("     写入前会自动备份 config.json（保留最近 10 份），事后可用 config restore 还原")
    if not a.yes:
        print("（干跑：要真写请加 --yes）", file=sys.stderr)
        return

    bak = backup_config(d)
    if bak is None:
        die("备份 config.json 失败 —— 拒绝写入（备份失败不提交）")

    # B3（2026-11-02）：原子写 + 乐观锁 —— mutate 基于每次新读的配置执行
    state = {"before": old_val}

    def mutate(cfg2):
        nd = cfg2
        for p2 in parts[:-1]:
            nd = nd[p2]
        state["before"] = nd[key]
        nd[key] = new_val
        return cfg2

    atomic_write_config(d, mutate)
    # 写后重读校验：JSON 可解析 + 原路径还能导航到目标键
    try:
        chk = json.loads(cf.read_text(encoding="utf-8"))
        cur = chk
        for p in parts[:-1]:
            cur = (cur or {}).get(p)
        if not isinstance(cur, dict) or key not in cur:
            die(f"写后校验失败：{a.path} 读不回 —— 配置可能损坏，请 config restore {bak.name}")
    except Exception as e:  # noqa: BLE001
        die(f"写后校验失败：{e} —— 请 config restore {bak.name}")
    # A4（2026-11-02）：变更入账本（reason 只记人明说的，不编造）
    from bili_radar.history import append_change
    cid = append_change(d, actor=getattr(a, "actor", "agent"), param=a.path,
                         before=state["before"], after=new_val,
                         reason=getattr(a, "reason", None))
    print(f"✅ 已写入 {a.path} = {new_val!r}（备份：{bak.name}；账本：{cid}）")


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