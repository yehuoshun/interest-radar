#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""comment.py —— 评论域：@ 主号 / 自发评论 / 楼中楼回复 / 评论快筛 / 可见性自检。"""
import hashlib as _h
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime

from bili_client import csrf_from_cookie, get, wbi_keys, wbi_sign
from core import API, UA, cookie_path, die, load_cookie, read_config, state_dir
from gates import (_ago_h, _record_write, _write_cooldown, _write_fail,
                   _write_gate, mention_log, note_failure, write_log)


def post_reply(bv: str, aid: int, text: str, reply_to, cookie: str, jct: str):
    """POST /x/v2/reply/add，返回 res json。网络异常 die。reply_to 非空 = 楼中楼回复。"""
    fields = {"type": 1, "oid": aid, "message": text, "csrf": jct,
              "plat": 1, "ordering": "heat"}
    if reply_to:
        fields["root"] = str(reply_to)
        fields["parent"] = str(reply_to)
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(f"{API}/x/v2/reply/add", data=body, headers={
        "User-Agent": UA, "Referer": f"https://www.bilibili.com/video/{bv}",
        "Cookie": cookie, "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception as e:  # noqa: BLE001
        die(f"发评论请求失败：{type(e).__name__}: {e}", 8)


def cmd_reply(a):
    """在视频评论区 @ 某人（默认干跑；真正发要 --yes + config 开关 + 昵称）。

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
    # 闸③：同一视频只发一条「主动 @ 推荐」；楼中楼回复（--reply-to）不受此限
    if (not getattr(a, "reply_to", None)) and f.exists() and any(
            a.bv in l and "mentioned" in l for l in f.read_text(encoding="utf-8").splitlines()):
        die(f"闸③：{a.bv} 已经 @ 过了 —— 同一视频只发一次", 5)

    # 闸⑥：滚动窗口频控（都在 config.json 的 mention 里，0 = 不限）—— 新号防高强度
    log = mention_log(d)
    per_hour = int(cfg.get("per_hour") if cfg.get("per_hour") is not None else 1)
    per_day = int(cfg.get("per_day") or 0)
    if per_hour > 0:
        n = sum(1 for r in log if _ago_h(r) < 1)
        if n >= per_hour:
            die(f"闸⑥：最近 1 小时已 @ 过 {n} 条（上限 {per_hour}/小时）—— 稍后再来", 11)
    if per_day > 0:
        n = sum(1 for r in log if _ago_h(r) < 24)
        if n >= per_day:
            die(f"闸⑥：最近 24 小时已 @ 过 {n} 条（上限 {per_day}/天）—— 不再发", 11)

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
    # 闸⑤：敏感词表（config.json 的 mention.forbid）—— 档案/项目名/路径一旦漏进来就拒发
    forbid = [w for w in (cfg.get("forbid") or []) if w and w in text]
    if forbid:
        die(f"闸⑤：正文命中敏感词 {forbid} —— 拒绝发（公开评论里不许出现这些）", 10)

    v = get(f"{API}/x/web-interface/view?bvid={a.bv}", cookie)["data"]
    aid, title = v["aid"], v.get("title")
    out = {"bvid": a.bv, "aid": aid, "title": title, "text": text,
           "url": f"https://www.bilibili.com/video/{a.bv}", "dry_run": not a.yes}
    if not a.yes:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("（干跑：要真发请加 --yes）", file=sys.stderr)
        return

    _write_cooldown(d, float(read_config().get("write", {}).get("cooldown_sec", 120) or 120))
    res = post_reply(a.bv, aid, text, getattr(a, "reply_to", None), cookie, jct)
    if res.get("code") != 0:
        # 风控类错误计数：连续失败就把开关关了（防账号被爆），等人来看
        hits = note_failure(d)
        if hits >= 3:
            cf = d / "config.json"
            try:
                cfgall = json.loads(cf.read_text(encoding="utf-8"))
                cfgall.setdefault("mention", {})["enabled"] = False
                cf.write_text(json.dumps(cfgall, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("⚠️ 连续 3 次发评论失败 → 已自动关掉 mention.enabled（防账号被爆），等本人来看", file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass
        die(f"发评论被拒：code={res.get('code')} msg={res.get('message')}（累计失败 {hits} 次）", 9)
    rpid = ((res.get("data") or {}).get("rpid_str") or (res.get("data") or {}).get("rpid"))
    # 发完自检：匿名看不看得到（阿瓦隆拦了就记一行，别人看得到才算真发出去）
    time.sleep(3)
    vis = None
    try:
        # ⚠️ visible_anon 只查顶层评论；楼中楼查不准 → 标 None（未验证）
        if not getattr(a, "reply_to", None):
            vis = visible_anon(a.bv, str(rpid), pages=2)
    except Exception:  # noqa: BLE001
        vis = None
    note = {True: "公开可见", False: "匿名不可见（可能被拦/审核中）", None: "未验证"}[vis]
    # 楼中楼回复记 `replied`（不含 mentioned），不触发阰③「同一视频只发一条」——
    # 那道闸只管「主动 @ 推荐」，而回复主号 @ 我的指令是另一类行为。
    kind = "replied" if getattr(a, "reply_to", None) else "mentioned"
    with f.open("a", encoding="utf-8") as fh:
        extra = f" | reply_to={a.reply_to}" if getattr(a, "reply_to", None) else ""
        fh.write(f"{time.strftime('%Y-%m-%d')} | bilibili | {a.bv} | {kind} | {title} | rpid={rpid}{extra} | {note}\n")
    with (d / "mention-log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                             "bv": a.bv, "rpid": rpid, "visible_anon": vis,
                             "kind": kind,
                             **({"reply_to": str(a.reply_to)} if getattr(a, "reply_to", None) else {})},
                            ensure_ascii=False) + "\n")
    out.update({"posted": True, "rpid": rpid, "visible_anon": vis, "verdict": note})
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_rate(a):
    """看 / 改频控参数（都在 config.json 的 mention 里，改完立即生效）。"""
    d = state_dir()
    cf = d / "config.json"
    cfg = read_config().get("mention") or {}
    if a.per_round is None and a.per_hour is None and a.per_day is None:
        log = mention_log(d)
        now = datetime.now()
        h1 = sum(1 for r in log if _ago_h(r) < 1)
        h24 = sum(1 for r in log if _ago_h(r) < 24)
        print(json.dumps({
            "per_round": cfg.get("per_round", 1),
            "per_hour": cfg.get("per_hour", 1),
            "per_day": cfg.get("per_day", 0),
            "实际用量": {"最近 1 小时": h1, "最近 24 小时": h24, "历史合计": len(log)},
            "说明": "0 = 不限；per_round = 每轮上限，per_hour/per_day = 滚动窗口上限",
        }, ensure_ascii=False, indent=2))
        return
    try:
        raw = json.loads(cf.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        raw = {}
    m = raw.setdefault("mention", {})
    for k, v in (("per_round", a.per_round), ("per_hour", a.per_hour), ("per_day", a.per_day)):
        if v is not None:
            m[k] = int(v)
    cf.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ 频控已更新：per_round={m.get('per_round')} / per_hour={m.get('per_hour')} / per_day={m.get('per_day')}")


def fetch_hot_comments(aid: int, cookie: str, ps: int = 10):
    """拉热门评论（sort=2 按热度），返回 [{user, like, content}]。接口验证于 bili_subtitle.py。"""
    url = f"{API}/x/v2/reply?type=1&oid={aid}&sort=2&ps={int(ps)}&nested=0"
    d = get(url, cookie)
    if d.get("code") != 0:
        return []
    out = []
    for r in (d.get("data") or {}).get("replies") or []:
        out.append({"user": ((r.get("member") or {}).get("uname") or ""),
                    "like": r.get("like", 0),
                    "content": ((r.get("content") or {}).get("message") or "")})
    return out


def cmd_comment_check(a):
    """轻量版评论区快筛（2026-10-27 老板拍板）：@ 分享前拉热评，规则统计疑似 AI 水军。

    只提示不拦截：命中警示阈值只影响推送文案（附一行提示），由本人定夺。
    规则全是确定性硬特征：数字昵称 / 昵称关键词（大肥鱼等）/ AI 句式 / 同质文案。
    """
    cfg = read_config().get("comment_check") or {}
    num = int(a.num or cfg.get("num", 10))
    warn_ratio = float(cfg.get("warn_ratio", 0.3))
    name_kw = [w for w in (cfg.get("name_keywords") or []) if w]
    ai_pats = [p for p in (cfg.get("ai_patterns") or []) if p]
    cookie = load_cookie()
    v = get(f"{API}/x/web-interface/view?bvid={a.bv}", cookie)["data"]
    cmts = fetch_hot_comments(v["aid"], cookie, num)
    if not cmts:
        print(json.dumps({"bv": a.bv, "total": 0, "verdict": "无评论可读"},
                         ensure_ascii=False, indent=2))
        return
    num_name = re.compile(r"^\d+$|^[\d\W]{6,}$")
    flags = {"数字昵称": 0, "昵称关键词": 0, "AI句式": 0, "同质文案": 0}
    hits = []
    contents = [c["content"] for c in cmts]
    dup = len(contents) - len(set(contents))
    if dup > 0:
        flags["同质文案"] = dup
    for c in cmts:
        why = []
        u = c["user"]
        if num_name.match(u) or (len(u) >= 8 and sum(ch.isdigit() for ch in u) / len(u) > 0.6):
            why.append("数字昵称")
            flags["数字昵称"] += 1
        if name_kw and any(k in u for k in name_kw):
            why.append("昵称关键词")
            flags["昵称关键词"] += 1
        if ai_pats and any(re.search(p, c["content"]) for p in ai_pats):
            why.append("AI句式")
            flags["AI句式"] += 1
        if why:
            hits.append({"user": u, "like": c["like"],
                         "content": c["content"][:60], "why": why})
    ratio = len(hits) / len(cmts)
    warn = ratio >= warn_ratio
    verdict = (f"⚠️ 评论区疑水军（{ratio:.0%} ≥ {warn_ratio:.0%}）——建议暂缓 @ 或推送时注明"
               if warn else f"正常（疑似 {ratio:.0%} < {warn_ratio:.0%}）")
    print(json.dumps({"bv": a.bv, "total": len(cmts), "suspicious": len(hits),
                      "ratio": round(ratio, 2), "warn_ratio": warn_ratio,
                      "flags": flags, "verdict": verdict, "hits": hits[:8]},
                     ensure_ascii=False, indent=2))


def cmd_comment(a):
    """自发评论（2026-10-27 老板放权：看到感兴趣的视频可以发，不强制 @ 主号、不属于雷达流程）。

    闸：① write.comment.enabled ② 显式 --yes ③ 非空且 ≤ 200 字
        ④ 敏感词（write.comment.forbid）fail-closed ⑤ 频控 ⑥ 同一视频只发一条
        ⑦ 连续失败 3 次自动关 write.comment.enabled
    """
    seg = _write_gate("comment")
    text = (a.text or "").strip()
    if not text:
        die("闸③：正文为空 —— 拒绝发", 7)
    if len(text) > 200:
        die(f"闸③：正文 {len(text)} 字 > 200 字上限", 7)
    forbid = [w for w in (seg.get("forbid") or []) if w and w in text]
    if forbid:
        die(f"闸④：正文命中敏感词 {forbid} —— 拒绝发（公开评论里不许出现这些）", 10)
    d = state_dir()
    if seg.get("same_video_once", True):
        prev = [r for r in write_log(d) if r.get("kind") == "comment" and r.get("bv") == a.bv]
        if prev:
            die(f"闸⑥：{a.bv} 已发过自发评论 —— 同一视频只发一条", 13)

    cookie = load_cookie()
    jct = csrf_from_cookie(cookie_path().read_text(encoding="utf-8"))
    if not jct:
        die("cookie 里没有 bili_jct（csrf）—— 没法发评论", 6)
    v = get(f"{API}/x/web-interface/view?bvid={a.bv}", cookie)["data"]
    aid, title = v["aid"], v.get("title")
    out = {"kind": "comment", "bv": a.bv, "aid": aid, "title": title, "text": text,
           "url": f"https://www.bilibili.com/video/{a.bv}", "dry_run": not a.yes}
    if not a.yes:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("（干跑：要真发请加 --yes）", file=sys.stderr)
        return
    _write_cooldown(d, float(read_config().get("write", {}).get("cooldown_sec", 120) or 120))
    fields = {"type": 1, "oid": aid, "message": text, "csrf": jct,
              "plat": 1, "ordering": "heat"}
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(f"{API}/x/v2/reply/add", data=body, headers={
        "User-Agent": UA, "Referer": f"https://www.bilibili.com/video/{a.bv}",
        "Cookie": cookie, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.load(r)
    except Exception as e:  # noqa: BLE001
        die(f"发评论请求失败：{type(e).__name__}: {e}", 8)
    if res.get("code") != 0:
        n = _write_fail(d, "comment")
        if n >= 3:
            cf = d / "config.json"
            try:
                cfgall = json.loads(cf.read_text(encoding="utf-8"))
                cfgall.setdefault("write", {}).setdefault("comment", {})["enabled"] = False
                cf.write_text(json.dumps(cfgall, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("⚠️ 连续 3 次自发评论失败 → 已自动关掉 write.comment.enabled（防账号被爆），等本人来看", file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass
        die(f"发评论被拒：code={res.get('code')} msg={res.get('message')}（累计失败 {n} 次）", 9)
    rpid = ((res.get("data") or {}).get("rpid_str") or (res.get("data") or {}).get("rpid"))
    time.sleep(3)
    vis = None
    try:
        vis = visible_anon(a.bv, str(rpid), pages=2)
    except Exception:  # noqa: BLE001
        vis = None
    note = {True: "公开可见", False: "匿名不可见（可能被拦/审核中）", None: "未验证"}[vis]
    _record_write(d, {"ts": datetime.now().isoformat(timespec="seconds"),
                      "kind": "comment", "bv": a.bv, "rpid": str(rpid), "chars": len(text),
                      "visible_anon": vis})
    out.update({"posted": True, "rpid": str(rpid), "visible_anon": vis, "verdict": note})
    print(json.dumps(out, ensure_ascii=False, indent=2))


def anon_get(url: str):
    """匿名 GET（不带 cookie）—— 用来验证"别人能不能看到"。"""
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