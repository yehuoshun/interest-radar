#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""browse.py —— 浏览域：登录检查 / 搜索 / 字幕 / seen 判重。"""
import json
import re
import time

from bili_radar.client import get, wbi_keys, wbi_sign
from bili_radar.core import API, clean, cookie_path, die, load_cookie, state_dir


# ───────────────────────────── 子命令 ─────────────────────────────


def cmd_check(_a):
    cookie = load_cookie()
    d, _ = wbi_keys(cookie)
    if not d.get("isLogin"):
        die("cookie 已失效（isLogin=false）—— 让小号重新登录后导出 cookie", 3)
    li = d.get("level_info") or {}
    print(json.dumps({
        "ok": True,
        "uname": d.get("uname"),
        "mid": str(d.get("mid"))[:3] + "***",
        "level": li.get("current_level"),
        "vip": (d.get("vipStatus") or 0) == 1,
        "cookie_file": str(cookie_path()),
    }, ensure_ascii=False, indent=2))


def cmd_search(a):
    cookie = load_cookie()
    _, mix = wbi_keys(cookie)
    out, seen = [], set()
    cutoff = time.time() - a.days * 86400 if a.days else None
    for page in range(1, a.pages + 1):
        q = wbi_sign({"search_type": "video", "keyword": a.kw, "page": page,
                      "page_size": 20, "order": a.order}, mix)
        data = get(f"{API}/x/web-interface/wbi/search/type?{q}", cookie).get("data") or {}
        res = data.get("result")
        if not isinstance(res, list):
            break
        for v in res:
            bv = v.get("bvid")
            if not bv or bv in seen:
                continue
            seen.add(bv)
            pub = v.get("pubdate") or 0
            if cutoff and pub and pub < cutoff:
                continue
            out.append({
                "bvid": bv,
                "title": clean(v.get("title")),
                "up": v.get("author"),
                "play": v.get("play"),
                "danmaku": v.get("video_review"),
                "duration": v.get("duration"),
                "pubdate": time.strftime("%Y-%m-%d", time.localtime(pub)) if pub else None,
                "desc": clean(v.get("description"))[:200],
                "url": f"https://www.bilibili.com/video/{bv}",
            })
        if len(res) < 20:
            break
        time.sleep(0.6)
    out = out[: max(1, a.num)]
    print(json.dumps({"keyword": a.kw, "count": len(out), "videos": out},
                     ensure_ascii=False, indent=2))


def cmd_feed(a):
    """首页推荐流（只读，2026-11-13）：像人一样刷首页，看系统推什么，而不是按关键词挖。

    和 `search` 的区别是「谁来决定看什么」：search 是带着问题找答案（雷达），
    feed 是让推荐算法开口（刷）——用来发现自己原本不会去搜的东西。
    """
    cookie = load_cookie()
    _, mix = wbi_keys(cookie)
    out, seen = [], set()
    for idx in range(1, max(1, a.rounds) + 1):
        q = wbi_sign({"web_location": 1430650, "y_num": 4, "fresh_type": 4,
                      "feed_version": "V8", "fresh_idx": idx, "fresh_idx_1h": idx,
                      "brush": idx - 1, "homepage_ver": 1, "ps": max(1, a.num)}, mix)
        data = get(f"{API}/x/web-interface/wbi/index/top/feed/rcmd?{q}", cookie).get("data") or {}
        items = data.get("item") or []
        if not items:
            break
        for it in items:
            bv = it.get("bvid")
            if not bv or bv in seen:
                continue
            seen.add(bv)
            st = it.get("stat") or {}
            _reason = it.get("rcmd_reason") or ""
            if isinstance(_reason, dict):  # 实测：有的条目给 {"content": "…", "reason_type": 1}
                _reason = _reason.get("content") or ""
            out.append({
                "bvid": bv,
                "title": clean(it.get("title")),
                "up": (it.get("owner") or {}).get("name"),
                "duration": f"{(it.get('duration') or 0) // 60}:{(it.get('duration') or 0) % 60:02d}",
                "play": st.get("view"),
                "danmaku": st.get("danmaku"),
                "like": st.get("like"),
                "reason": clean(_reason),
                "url": f"https://www.bilibili.com/video/{bv}",
            })
        time.sleep(1.2)
    print(json.dumps({"count": len(out), "videos": out}, ensure_ascii=False, indent=2))


def fetch_subtitle_text(cookie: str, bv: str, cid: int):
    """取一个字幕的全文。**必须用 wbi 签名的 `player/wbi/v2`**。

    🔴 2026-10-15 实测事故：不带签名的旧接口 `x/player/v2` 会**返回别的视频的字幕**
      （同一个视频两次拿到"核能"和"京都米其林"两段完全无关的内容）—— 拿它判断内容
      等于拿别人的字幕做结论。旧接口只当兼容，不用。
    返回 (text, lan)；拿不到就 (None, None)。
    """
    _, mix = wbi_keys(cookie)
    p = get(f"{API}/x/player/wbi/v2?" + wbi_sign({"bvid": bv, "cid": cid}, mix), cookie)
    subs = ((p.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
    subs = [s for s in subs if (s.get("subtitle_url") or "").strip()]
    if not subs:
        return None, None
    pick = next((s for s in subs if str(s.get("lan", "")).startswith("zh")), subs[0])
    u = pick.get("subtitle_url") or ""
    if u.startswith("//"):
        u = "https:" + u
    body = get(u, cookie).get("body") or []
    lines = [re.sub(r"\s+", " ", b.get("content", "")).strip() for b in body]
    text = "".join(l for l in lines if l)
    return (text or None), pick.get("lan")


def cmd_sub(a):
    cookie = load_cookie()
    v = get(f"{API}/x/web-interface/view?bvid={a.bv}", cookie)["data"]
    cid, title, dur = v["cid"], v.get("title"), v.get("duration") or 0
    text, lan = fetch_subtitle_text(cookie, a.bv, cid)
    if not text:
        print("NO_SUBTITLE")
        return
    # 🔴 合理性校验：字幕字数 / 时长 的"语速"得在人类区间（3~15 字/秒）
    rate = len(text) / dur if dur else 0
    suspect = bool(dur) and (rate > 15 or rate < 0.8)
    if suspect:
        again, _ = fetch_subtitle_text(cookie, a.bv, cid)
        if again != text:
            print(json.dumps({"bvid": a.bv, "title": title, "suspect": True,
                              "reason": f"语速异常 {rate:.1f} 字/秒，且两次结果不一致 —— 字幕不可信",
                              "chars": len(text), "duration": dur}, ensure_ascii=False))
            return
    print(json.dumps({
        "bvid": a.bv, "title": title, "lan": lan,
        "chars": len(text), "lines": len(text), "duration": dur,
        "rate": round(rate, 2), "suspect": suspect,
        "text": text[:a.max_chars],
        "truncated": len(text) > a.max_chars,
    }, ensure_ascii=False))


def cmd_seen(a):
    f = state_dir() / "seen.md"
    args = a.rest or []
    if a.action == "check":
        if not args:
            die("用法：seen check <BV号>")
        bv = args[0]
        hit = False
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if bv in line:
                    hit = True
                    print(line)
        print("SEEN" if hit else "NEW")
        return
    if a.action == "add":
        # seen add <日期> <BV号> <verdict> [标题...]
        if len(args) < 3:
            die("用法：seen add <日期> <BV号> <verdict> [标题...]")
        date, bv, verdict, title = args[0], args[1], args[2], " ".join(args[3:])
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(f"{date} | bilibili | {bv} | {verdict} | {title}\n")
        print(f"OK 已记：{bv} {verdict}")
        return
    die("用法：seen check <BV号> | seen add <日期> <BV号> <verdict> [标题]")