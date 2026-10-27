#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notify.py —— 通知与私信域：@我的/回复通知、私信读（dm）与私信发（msg）。

dm 水位约定（2026-10-27 修）：水位只按对方（主号）消息推进，自己消息不推水位、
new_only 不输出自己消息 —— 防止自己发的私信盖过主号回复。
"""
import json
import random as _random
import time
from datetime import datetime

from bili_radar.client import csrf_from_cookie, get, post_form
from bili_radar.core import API, UA, cookie_path, die, load_cookie, read_config, state_dir
from bili_radar.gates import _record_write, _write_cooldown, _write_fail, _write_gate


def cmd_msg(a):
    """给白名单里的 mid 发私信（默认只有主号）。默认干跑；真发要 --yes + config 开关。

    闸：① write.message.enabled ② 显式 --yes ③ 正文 ≤200 字 ④ 敏感词 fail-closed
        ⑤ 频控 ⑥ 白名单 allow_mid（硬闸，只准发这些人）
    """
    seg = _write_gate("message")
    mid = int(a.mid or 0)
    if mid <= 0:
        die("--mid 必须是正数", 7)
    allow = [int(x) for x in (seg.get("allow_mid") or [])]
    if allow and mid not in allow:
        die(f"闸⑥：{mid} 不在 write.message.allow_mid 白名单（{allow}）里 —— 拒绝发私信", 10)
    text = (a.text or "").strip()
    if not text:
        die("闸③：正文为空 —— 拒绝发", 7)
    if len(text) > 200:
        die(f"闸③：正文 {len(text)} 字 > 200 字上限", 7)
    forbid = [w for w in (seg.get("forbid") or []) if w and w in text]
    if forbid:
        die(f"闸④：正文命中敏感词 {forbid} —— 拒绝发（私信里不许出现这些）", 10)

    cookie = load_cookie()
    jct = csrf_from_cookie(cookie_path().read_text(encoding="utf-8"))
    if not jct:
        die("cookie 里没有 bili_jct（csrf）—— 没法发私信", 6)
    nav = get(f"{API}/x/web-interface/nav", cookie)["data"]
    sender = int(nav.get("mid") or 0)
    out = {"kind": "message", "to_mid": mid, "text": text, "chars": len(text), "dry_run": not a.yes}
    if not a.yes:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("（干跑：要真发请加 --yes）", file=sys.stderr)
        return
    _write_cooldown(state_dir(), float(read_config().get("write", {}).get("cooldown_sec", 120) or 120))
    dev = "".join(_random.choice("0123456789ABCDEF") for _ in range(8))
    dev_id = f"{dev}-{dev[:4]}-{dev[4:]}-{dev[:4]}-{dev + dev[:4]}"[:36]
    fields = {
        "msg[sender_uid]": str(sender), "msg[receiver_id]": str(mid),
        "msg[receiver_type]": "1", "msg[msg_type]": "1", "msg[dev_id]": dev_id,
        "msg[timestamp]": str(int(time.time())),
        "msg[content]": json.dumps({"content": text}, ensure_ascii=False),
        "csrf": jct, "csrf_token": jct, "build": "0", "mobi_app": "web", "platform": "web",
    }
    res = post_form("https://api.vc.bilibili.com/web_im/v1/web_im/send_msg", fields, cookie,
                    "https://message.bilibili.com/")
    if res.get("code") != 0:
        n = _write_fail(state_dir(), "message")
        die(f"发私信被拒：code={res.get('code')} msg={res.get('message')}（今日失败 {n} 次）", 9)
    mk = (res.get("data") or {}).get("msg_key")
    _record_write(state_dir(), {"ts": datetime.now().isoformat(timespec="seconds"),
                                "kind": "message", "to_mid": mid, "msg_key": str(mk)})
    out.update({"posted": True, "msg_key": str(mk), "sender_mid": sender})
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_dm(a):
    """读私信正文（只读！不发送、不回、不标记已读）。

    默认读 config.json 的 mention.mid（主号）那条会话；--new-only 用时间水位只列新的
    （水位落 dm-state.json）。
    实测 2026-10-19：`svr_sync/fetch_session_msgs` 只要 cookie 就能拿到正文（不用 app 签名）——
    与旧文档「私信正文读不到」不符，已更正。
    """
    cfg = read_config()
    mid = int(a.mid or (cfg.get("mention") or {}).get("mid") or 0)
    if not mid:
        die("不知道读谁的会话：给 --mid，或在 config.json 的 mention.mid 里配主号 mid", 7)
    cookie = load_cookie()
    me = int((get(f"{API}/x/web-interface/nav", cookie)["data"].get("mid")) or 0)
    url = ("https://api.vc.bilibili.com/svr_sync/v1/svr_sync/fetch_session_msgs"
           f"?talker_id={mid}&session_type=1&size={int(a.size)}&build=0&mobi_app=web")
    msgs = ((get(url, cookie).get("data") or {}).get("messages") or [])

    d = state_dir()
    sf = d / "dm-state.json"
    try:
        state = json.loads(sf.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    last = int((state.get(str(mid)) or {}).get("last_ts") or 0)

    out = []
    max_ts = last
    for m in msgs:
        ts = int(m.get("timestamp") or 0)
        sender = int(m.get("sender_uid") or 0)
        # 水位只按对方（主号）消息推进（2026-10-27 对齐 whale：自己消息不推水位，
        # 否则自己发的私信会盖过主号回复导致被跳过）
        if sender == mid:
            max_ts = max(max_ts, ts)
        if a.new_only and ts <= last:
            continue
        # new_only 只关心对方说什么，不输出自己发的消息
        if a.new_only and sender == me:
            continue
        text = m.get("content")
        try:
            text = json.loads(text).get("content", text)
        except Exception:  # noqa: BLE001
            pass
        out.append({"ts": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
                    "ts_raw": ts,
                    "from": "主号" if sender == mid else "我",
                    "from_mid": m.get("sender_uid"),
                    "text": str(text)})
    out.sort(key=lambda x: x["ts_raw"])
    if not a.new_only or max_ts > last:
        state[str(mid)] = {"last_ts": max_ts, "last_read": datetime.now().isoformat(timespec="seconds")}
        try:
            sf.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    print(json.dumps({"talker_id": mid, "me": me, "new_only": bool(a.new_only),
                      "count": len(out), "water_level": max_ts, "messages": out},
                     ensure_ascii=False, indent=2))


def cmd_notify(a):
    """谁能找到我：读自己的 B站 通知（@我的 / 回复我的 / 未读计数）。

    只读 @ 和回复的**元数据**（谁、何时、在哪个视频），不写正文。
    私信正文读不到（要 app 签名），这里只报未读计数。
    """
    cookie = load_cookie()
    un = radar_unread(cookie)
    out = {"unread": un, "at": [], "reply": []}

    def norm(items, kind):
        rows = []
        for it in items or []:
            u = it.get("user") or {}
            item = it.get("item") or {}
            c = it.get("content") or {}
            if kind == "reply":
                # 回复：item.source_content 才是对方说的话；title 是被回复的那条
                rows.append({
                    "from": u.get("nickname"),
                    "mid": u.get("mid"),
                    "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(it.get("reply_time") or 0)),
                    "text": item.get("source_content") or "",       # 对方回复内容
                    "replied_to": item.get("title") or "",          # 他在回复什么
                    "uri": item.get("uri"),
                })
            else:
                rows.append({
                    "from": u.get("nickname"),
                    "mid": u.get("mid"),
                    "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(it.get("at_time") or it.get("time") or 0)),
                    # @我的正文在 item.source_content（与 reply 同源）；content.message 常为空
                    "text": item.get("source_content") or c.get("message") or c.get("title") or "",
                    "rpid": item.get("source_id"),   # 他那条评论的 rpid → 可用 --reply-to 回楼中楼
                    "title": item.get("title"),
                    "uri": item.get("uri"),
                })
        return rows

    out["at"] = norm((get(f"{API}/x/msgfeed/at?build=0&mobi_app=web", cookie).get("data") or {}).get("items"), "at")
    out["reply"] = norm((get(f"{API}/x/msgfeed/reply?build=0&mobi_app=web", cookie).get("data") or {}).get("items"), "reply")
    out["summary"] = (f"@我 {out['unread'].get('at', 0)} 条、回复 {out['unread'].get('reply', 0)} 条、"
                      f"赞 {out['unread'].get('like', 0)}、私信未读 {out['unread'].get('chat', 0)}")

    # ⚠️ 读过就可能把"未读"清掉 —— 所以判新要用**时间水位**，不能靠未读计数
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