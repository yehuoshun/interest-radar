#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dynamic.py —— 动态域：发动态 / 删动态（2026-10-19 老板放开）。

删动态不写冷却（纠错优先）；发动态走 post_json（form 编码会 -400）。
"""
import json
from datetime import datetime

from bili_client import csrf_from_cookie, get, post_form, post_json
from core import API, cookie_path, die, load_cookie, read_config, state_dir
from gates import _record_write, _write_cooldown, _write_fail, _write_gate


def cmd_dynamic(a):
    """发一条动态（默认干跑；真发要 --yes + config 开关）。只发「今天读到/干了什么」的本体视角，不发档案。

    闸：① write.dynamic.enabled ② 显式 --yes ③ 正文非空且 ≤200 字
        ④ 敏感词 fail-closed ⑤ 频控 ⑥ 连续失败 3 次自动关 write.dynamic.enabled
    """
    _write_gate("dynamic")
    text = (a.text or "").strip()
    if not text:
        die("闸③：正文为空 —— 拒绝发", 7)
    if len(text) > 200:
        die(f"闸③：正文 {len(text)} 字 > 200 字上限", 7)
    seg = (read_config().get("write") or {}).get("dynamic") or {}
    forbid = [w for w in (seg.get("forbid") or []) if w and w in text]
    if forbid:
        die(f"闸④：正文命中敏感词 {forbid} —— 拒绝发（动态里不许出现这些）", 10)

    cookie = load_cookie()
    jct = csrf_from_cookie(cookie_path().read_text(encoding="utf-8"))
    if not jct:
        die("cookie 里没有 bili_jct（csrf）—— 没法发动态", 6)
    out = {"kind": "dynamic", "text": text, "chars": len(text), "dry_run": not a.yes}
    if not a.yes:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("（干跑：要真发请加 --yes）", file=sys.stderr)
        return
    _write_cooldown(state_dir(), float(read_config().get("write", {}).get("cooldown_sec", 120) or 120))
    # 实测（2026-10-19）：本接口只吃 JSON body `{"dyn_req":{...}}`；
    # 用 application/x-www-form-urlencoded 会 -400 请求错误，raw dyn_req 会 4100001 参数错误。
    dyn_req = {"content": {"contents": [{"raw_text": text, "type": 1, "biz_id": ""}]}, "scene": 1}
    res = post_json(f"{API}/x/dynamic/feed/create/dyn?platform=web&csrf={jct}",
                    {"dyn_req": dyn_req}, cookie, "https://www.bilibili.com/")
    if res.get("code") != 0:
        n = _write_fail(state_dir(), "dynamic")
        die(f"发动态被拒：code={res.get('code')} msg={res.get('message')}（今日失败 {n} 次）", 9)
    d0 = res.get("data") or {}
    dyn_id = d0.get("dyn_id_str") or d0.get("dyn_id")
    _record_write(state_dir(), {"ts": datetime.now().isoformat(timespec="seconds"),
                                "kind": "dynamic", "dyn_id": str(dyn_id), "chars": len(text)})
    out.update({"posted": True, "dyn_id": str(dyn_id),
                "url": f"https://t.bilibili.com/{dyn_id}"})
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_dynamic_del(a):
    """删一条自己发的动态（发错了能收回来）。闸同 cmd_dynamic（开关 + --yes），不受发帖频控限制。"""
    _write_gate("dynamic", rate=False)
    if not str(a.dyn_id).isdigit():
        die("--dyn-id 必须是数字动态 id", 7)
    cookie = load_cookie()
    jct = csrf_from_cookie(cookie_path().read_text(encoding="utf-8"))
    out = {"kind": "dynamic-del", "dyn_id": str(a.dyn_id), "dry_run": not a.yes}
    if not a.yes:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("（干跑：要真删请加 --yes）", file=sys.stderr)
        return
    res = post_form("https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/rm_dynamic",
                    {"dynamic_id": str(a.dyn_id), "csrf": jct}, cookie, "https://t.bilibili.com/")
    if res.get("code") != 0:
        die(f"删动态被拒：code={res.get('code')} msg={res.get('message')}", 9)
    _record_write(state_dir(), {"ts": datetime.now().isoformat(timespec="seconds"),
                                "kind": "dynamic-del", "dyn_id": str(a.dyn_id)})
    out["deleted"] = True
    print(json.dumps(out, ensure_ascii=False, indent=2))