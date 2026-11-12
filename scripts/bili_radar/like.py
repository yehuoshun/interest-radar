#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""like.py —— 点赞域（2026-11-13 老板放开：「遇到喜欢的点赞」）。

只解决一件事：读到真好的一条，能像人一样点个赞，而不是只把标题记进报告。
不点赞号（那是自动涨活跃度）、不连点（同一视频只点一次）、不隐藏（点赞是公开行为）。

闸：① write.like.enabled ② 显式 --yes ③ 同一视频只点一次
    ④ 写冷却（write.cooldown_sec）⑤ 频控（write.like.per_hour / per_day）
    ⑥ 连续失败 3 次自动关掉 write.like.enabled
取消赞：`like --bv BV --cancel --yes`（纠错优先，不冷却、不计频控）
"""
import json
import sys
from datetime import datetime

from bili_radar.client import csrf_from_cookie, get, post_form
from bili_radar.core import API, cookie_path, die, load_cookie, read_config, state_dir
from bili_radar.gates import (_record_write, _write_cooldown, _write_fail, _write_gate,
                              write_log)


def cmd_like(a):
    """给某条视频点赞 / 取消赞（默认干跑；真发要 --yes + config 开关）。"""
    cancel = bool(getattr(a, "cancel", False))
    seg = _write_gate("like", rate=not cancel)
    d = state_dir()
    if seg.get("same_video_once", True) and not cancel:
        prev = [r for r in write_log(d) if r.get("kind") == "like" and r.get("bv") == a.bv]
        if prev:
            die(f"闸③：{a.bv} 已经赞过 —— 同一视频只点一次", 13)

    cookie = load_cookie()
    jct = csrf_from_cookie(cookie_path().read_text(encoding="utf-8"))
    if not jct:
        die("cookie 里没有 bili_jct（csrf）—— 没法点赞", 6)

    v = get(f"{API}/x/web-interface/view?bvid={a.bv}", cookie)["data"]
    aid, title = v["aid"], v.get("title")
    like = 0 if cancel else 1
    out = {"kind": "like", "bv": a.bv, "aid": aid, "title": title,
           "like": like, "dry_run": not a.yes}
    if not a.yes:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("（干跑：真要" + ("取消赞" if cancel else "点赞") + "请加 --yes）", file=sys.stderr)
        return

    if not cancel:
        _write_cooldown(d, float(read_config().get("write", {}).get("cooldown_sec", 120) or 120))
    res = post_form(f"{API}/x/web-interface/archive/like",
                    {"aid": aid, "like": like, "csrf": jct}, cookie,
                    f"https://www.bilibili.com/video/{a.bv}")
    if res.get("code") != 0:
        n = _write_fail(d, "like")
        die(f"{'取消赞' if cancel else '点赞'}被拒：code={res.get('code')} "
            f"msg={res.get('message')}（今日失败 {n} 次）", 9)
    _record_write(d, {"ts": datetime.now().isoformat(timespec="seconds"),
                      "kind": "unlike" if cancel else "like",
                      "bv": a.bv, "aid": aid})
    out["done"] = True
    print(json.dumps(out, ensure_ascii=False, indent=2))
