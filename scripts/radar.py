#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar.py —— 兴趣雷达的"手脚"（确定性那一半：取数、判重、记反馈、算权重）
判断那一半（值不值得）由模型按 interests/charter.md 做，不在这里。

子命令：
  check                                    # 校验 cookie 是否有效（打印昵称/mid）
  search  --kw 关键词 [--num 20] [--days 7] [--order pubdate|click|totalrank]
  sub     BV号                             # 打印字幕纯文本；无字幕则打印 NO_SUBTITLE
  seen    check BV号 | seen add <日期> <BV号> <verdict> <标题>
  feedback --topic 主题 --signal like|skip [--bv BV号] [--score 3] [--note 备注]
  stats                                    # 打印 weights 汇总（给"每周提议"用）

约定：
  · cookie 文件：~/.openclaw/secrets/bilibili-cookies.txt（可用 BILI_COOKIE_FILE 覆盖）
  · 状态目录 ：<workspace>/interests（可用 INTERESTS_DIR 覆盖）
  · 只读不写：本脚本不提供任何发评论/发动态的接口（红线）
"""
import argparse
import hashlib
import json
import os
import random as _random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
API = "https://api.bilibili.com"

# wbi 签名用的混淆表（B站前端同款）
MIX = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
       33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
       26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
       20, 34, 44, 52]


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def cookie_path() -> Path:
    p = os.environ.get("BILI_COOKIE_FILE")
    return Path(p) if p else Path.home() / ".openclaw" / "secrets" / "bilibili-cookies.txt"


def state_dir() -> Path:
    p = os.environ.get("INTERESTS_DIR")
    if p:
        return Path(p)
    # 脚本在 <workspace>/skills/interest-radar/scripts/ 下
    return Path(__file__).resolve().parents[3] / "interests"


def load_cookie() -> str:
    f = cookie_path()
    if not f.exists():
        die(f"没有 cookie 文件：{f}（读字幕必须登录）")
    raw = f.read_text(encoding="utf-8").strip()
    if "=" not in raw:
        die(f"cookie 文件格式不对：{f}")
    return "; ".join(l.strip().rstrip(";") for l in raw.splitlines() if l.strip())


def get(url: str, cookie: str, tries: int = 3):
    """带 UA/Referer/Cookie 的 GET，返回 json。网络抖动重试，风控显式报错。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": "https://www.bilibili.com/",
                "Cookie": cookie,
                "Accept": "application/json, text/plain, */*",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.load(r)
            # 有的接口（如字幕 CDN）直接返回裸 JSON，没有 code 字段 —— 视为成功
            if not isinstance(data, dict) or "code" not in data:
                return data
            code = data.get("code")
            if code == 0:
                return data
            if code == -412:
                die("被风控（-412）：换 IP 或稍后再试（沙箱出口是阿里云段，容易踩）", 2)
            msg = str(data.get("message") or "")
            if "v_voucher" in json.dumps(data.get("data") or {}, ensure_ascii=False) or "风控" in msg:
                die("被风控（v_voucher）：需要干净的出口 IP 或过验证", 2)
            last = f"code={code} msg={msg}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(0.8 * (i + 1))
    die(f"请求失败：{url} → {last}")


def wbi_keys(cookie: str):
    d = get(f"{API}/x/web-interface/nav", cookie)["data"]
    img, sub = d["wbi_img"]["img_url"], d["wbi_img"]["sub_url"]
    ik = img.rsplit("/", 1)[-1].split(".")[0]
    sk = sub.rsplit("/", 1)[-1].split(".")[0]
    return d, "".join((ik + sk)[i] for i in MIX)[:32]


def wbi_sign(params: dict, mix: str) -> str:
    p = dict(params, wts=int(time.time()))
    q = urllib.parse.urlencode(sorted(p.items()))
    return q + "&w_rid=" + hashlib.md5((q + mix).encode()).hexdigest()


def clean(s: str) -> str:
    return urllib.parse.unquote(re.sub(r"<[^>]+>", "", s or "")).strip()


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


def cmd_sub(a):
    cookie = load_cookie()
    v = get(f"{API}/x/web-interface/view?bvid={a.bv}", cookie)["data"]
    cid, title = v["cid"], v.get("title")
    p = get(f"{API}/x/player/v2?bvid={a.bv}&cid={cid}", cookie)
    subs = ((p.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
    # 有些条目 subtitle_url 是空的（占位）—— 先过滤，优先中文
    subs = [s for s in subs if (s.get("subtitle_url") or "").strip()]
    if not subs:
        print("NO_SUBTITLE")
        return
    pick = next((s for s in subs if str(s.get("lan", "")).startswith("zh")), subs[0])
    u = pick.get("subtitle_url") or ""
    if u.startswith("//"):
        u = "https:" + u
    body = get(u, cookie).get("body") or []
    lines = [re.sub(r"\s+", " ", b.get("content", "")).strip() for b in body]
    lines = [l for l in lines if l]
    text = "".join(lines)  # 字幕是逐句切片，直接拼
    print(json.dumps({
        "bvid": a.bv, "title": title, "lan": pick.get("lan"),
        "chars": len(text), "lines": len(lines),
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


def read_config():
    f = state_dir() / "config.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def csrf_from_cookie(raw: str) -> str:
    m = re.search(r"bili_jct=([^;\s]+)", raw)
    return m.group(1) if m else ""


def cmd_reply(a):
    """在视频评论區 @ 某人（默认干跑；真正发要 --yes + config 开关 + 昵称）。

    闸（四道，全在代码里，不靠提示词）：
      ① config.json 的 mention.enabled 必须为 true，且 mention.name 非空
      ② 必须显式 --yes（默认干跑）
      ③ 同一 BV 只发一次（查 seen.md 里的 mentioned 记录）
      ④ 正文 ≤ 150 字，且必须含 @nickname
    """
    cfg = read_config().get("mention") or {}
    name = (cfg.get("name") or "").strip()
    if not cfg.get("enabled"):
        die("闸①：config.json 里 mention.enabled 不是 true —— 拒绝发评论", 4)
    if not name:
        die("闸①：config.json 里 mention.name 为空（@ 谁？）—— 拒绝发评论", 4)

    d = state_dir()
    f = d / "seen.md"
    if f.exists() and any(a.bv in l and "mentioned" in l for l in f.read_text(encoding="utf-8").splitlines()):
        die(f"闸③：{a.bv} 已经 @ 过了 —— 同一视频只发一次", 5)

    cookie = load_cookie()
    raw = cookie_path().read_text(encoding="utf-8")
    jct = csrf_from_cookie(raw)
    if not jct:
        die("cookie 里没有 bili_jct（csrf）—— 没法发评论", 6)

    text = (a.text or f"@{name} 这个值得看一眼").strip()
    if name not in text:
        text = f"@{name} {text}"
    if len(text) > 150:
        die(f"闸④：正文 {len(text)} 字 > 150 字上限", 7)

    v = get(f"{API}/x/web-interface/view?bvid={a.bv}", cookie)["data"]
    aid, title = v["aid"], v.get("title")
    out = {"bvid": a.bv, "aid": aid, "title": title, "text": text,
           "url": f"https://www.bilibili.com/video/{a.bv}", "dry_run": not a.yes}
    if not a.yes:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("（干跑：要真发请加 --yes）", file=sys.stderr)
        return

    body = urllib.parse.urlencode({
        "type": 1, "oid": aid, "message": text, "csrf": jct,
        "plat": 1, "ordering": "heat",
    }).encode()
    req = urllib.request.Request(f"{API}/x/v2/reply/add", data=body, headers={
        "User-Agent": UA, "Referer": f"https://www.bilibili.com/video/{a.bv}",
        "Cookie": cookie, "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.load(r)
    except Exception as e:  # noqa: BLE001
        die(f"发评论请求失败：{type(e).__name__}: {e}", 8)
    if res.get("code") != 0:
        die(f"发评论被拒：code={res.get('code')} msg={res.get('message')}", 9)
    rpid = ((res.get("data") or {}).get("rpid_str") or (res.get("data") or {}).get("rpid"))
    # 发完自检：匿名看不看得到（阿瓦隆拦了就记一行，别人看得到才算真发出去）
    time.sleep(3)
    vis = None
    try:
        vis = visible_anon(a.bv, str(rpid), pages=2)
    except Exception:  # noqa: BLE001
        vis = None
    note = {True: "公开可见", False: "匿名不可见（可能被拦/审核中）", None: "未验证"}[vis]
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d')} | bilibili | {a.bv} | mentioned | {title} | rpid={rpid} | {note}\n")
    out.update({"posted": True, "rpid": rpid, "visible_anon": vis, "verdict": note})
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_notify(a):
    """谁能找到我：读自己的 B站 通知（@我的 / 回复我的 / 未读计数）。

    只读 @ 和回复的**元数据**（谁、何时、在哪个视频），不写正文。
    私信正文读不到（要 app 签名），这里只报未读计数。
    """
    cookie = load_cookie()
    un = radar_unread(cookie)
    out = {"unread": un, "at": [], "reply": []}

    def norm(items, tkey):
        rows = []
        for it in items or []:
            u = it.get("user") or {}
            item = it.get("item") or {}
            c = it.get("content") or {}
            rows.append({
                "from": u.get("nickname"),
                "mid": u.get("mid"),
                "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(
                    it.get(tkey) or it.get("time") or 0)),
                "title": item.get("title"),
                "uri": item.get("uri"),
                "text": c.get("message") or c.get("title") or "",
            })
        return rows

    out["at"] = norm((get(f"{API}/x/msgfeed/at?build=0&mobi_app=web", cookie).get("data") or {}).get("items"), "at_time")
    out["reply"] = norm((get(f"{API}/x/msgfeed/reply?build=0&mobi_app=web", cookie).get("data") or {}).get("items"), "reply_time")
    out["summary"] = (f"@我 {out['unread'].get('at', 0)} 条、回复 {out['unread'].get('reply', 0)} 条、"
                      f"赞 {out['unread'].get('like', 0)}、私信未读 {out['unread'].get('chat', 0)}")

    # ⚠️ 读过就可能把“未读”清掉 —— 所以判新要用**时间水位**，不能靠未读计数
    if a.new_only:
        wf = state_dir() / "notify-state.json"
        try:
            wm = json.loads(wf.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            wm = {}
        for k in ("at", "reply"):
            last = wm.get(k) or ""
            fresh = [r for r in out[k] if r["time"] > last]
            if out[k]:
                wm[k] = max(r["time"] for r in out[k])
            out[k] = fresh
            out[f"{k}_new"] = len(fresh)
        wf.parent.mkdir(parents=True, exist_ok=True)
        wf.write_text(json.dumps(wm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


def radar_unread(cookie):
    return get(f"{API}/x/msgfeed/unread", cookie).get("data") or {}


def anon_get(url: str):
    """匿名 GET（不带 cookie）—— 用来验证“别人能不能看到”。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json, text/plain, */*",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def visible_anon(bv: str, rpid: str, pages: int = 3):
    """别人（未登录）能不能看到这条评论。返回 True/False/None(=查不准)。

    ⚠️ 楼中楼不算 —— 只查顶层（阿瓦隆拦楼中楼时接口对所有人都返回 0，查不出真假）。
    """
    import hashlib as _h
    _, mix = wbi_keys(load_cookie())
    aid = get(f"{API}/x/web-interface/view?bvid={bv}", load_cookie())["data"]["aid"]
    found = False
    for mode in (2, 3):
        nxt = 0
        for _ in range(pages):
            q = wbi_sign({"type": 1, "oid": aid, "mode": mode, "next": nxt, "ps": 20}, mix)
            try:
                d = anon_get(f"{API}/x/v2/reply/wbi/main?{q}").get("data") or {}
            except Exception:  # noqa: BLE001
                return None
            for x in (d.get("replies") or []):
                if str(x.get("rpid")) == str(rpid):
                    found = True
            nxt = (d.get("cursor") or {}).get("next") or 0
            if not nxt:
                break
        if found:
            return True
    return False


def cmd_check_reply(a):
    v = visible_anon(a.bv, a.rpid)
    verdict = {True: "公开可见 ✅", False: "匿名看不到 ⚠️（可能被阿瓦隆拦/审核中，主号自己能看到不代表公开）",
               None: "查询失败（网络/风控）"}[v]
    print(json.dumps({"bvid": a.bv, "rpid": a.rpid, "visible_anon": v, "verdict": verdict},
                     ensure_ascii=False, indent=2))


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
    t[a.signal] = int(t.get(a.signal, 0)) + 1
    n = t["like"] + t["skip"]
    t["weight"] = round(t["like"] / n, 3) if n else 0.0
    t["last"] = time.strftime("%Y-%m-%d")
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


def main():
    ap = argparse.ArgumentParser(description="兴趣雷达 · 取数/判重/反馈")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check").set_defaults(fn=cmd_check)

    s = sub.add_parser("search")
    s.add_argument("--kw", required=True)
    s.add_argument("--num", type=int, default=20)
    s.add_argument("--pages", type=int, default=1)
    s.add_argument("--days", type=int, default=7)
    s.add_argument("--order", default="pubdate")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("sub")
    s.add_argument("bv")
    s.add_argument("--max-chars", dest="max_chars", type=int, default=6000)
    s.set_defaults(fn=cmd_sub)

    s = sub.add_parser("seen")
    s.add_argument("action", choices=["check", "add"])
    s.add_argument("rest", nargs="*")
    s.set_defaults(fn=cmd_seen)

    s = sub.add_parser("reply")
    s.add_argument("--bv", required=True)
    s.add_argument("--text", help="评论正文（默认「@昵称 这个值得看一眼」）")
    s.add_argument("--yes", action="store_true", help="真正发出（默认干跑，只打印会发什么）")
    s.set_defaults(fn=cmd_reply)

    s = sub.add_parser("check-reply")
    s.add_argument("--bv", required=True)
    s.add_argument("--rpid", required=True)
    s.set_defaults(fn=cmd_check_reply)

    s = sub.add_parser("feedback")
    s.add_argument("--topic", required=True)
    s.add_argument("--signal", required=True, choices=["like", "skip"])
    s.add_argument("--bv")
    s.add_argument("--score", type=int)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_feedback)

    s = sub.add_parser("notify")
    s.add_argument("--new-only", dest="new_only", action="store_true",
                   help="只列比上次新的（用时间水位，不靠未读计数）")
    s.set_defaults(fn=cmd_notify)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
