#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""draft.py —— 陌生人草稿审核（2026-10-27 老板拍板试点）。

陌生人提问类评论 → 草稿（≤150 字 + 敏感词 fail-closed + 水军昵称拒 + 同人 30 天限频）
→ 本人审批（微信 / B站私信）→ approve 才发（楼中楼）；24h 未审批自动作废。
"""
import json
import sys
import time
from datetime import datetime

from bili_radar.client import csrf_from_cookie, get
from bili_radar.comment import post_reply
from bili_radar.core import API, cookie_path, die, load_cookie, read_config, state_dir
from bili_radar.gates import _write_cooldown


def drafts_file():
    return state_dir() / "drafts.jsonl"


def load_drafts():
    f = drafts_file()
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    return out


def save_drafts(recs):
    with drafts_file().open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def cmd_draft(a):
    """陌生人草稿审核（2026-10-27 老板拍板试点：只回提问类，草稿→本人审批→才发）。

    闸：① config.draft.enabled ② 正文 ≤150 字 + 敏感词 fail-closed
        ③ 超过 24h 未审批自动作废 ④ 频控 12h≤1 / 24h≤2（可配）
        ⑤ 必须 --yes 真发（默认干跑） ⑥ 连续失败 3 次标记 failed
        ⑦ 同人 30 天只回一次 ⑧ 对方昵称命中水军关键词（大肥鱼等）拒入稿
    """
    recs = load_drafts()
    if a.action == "new":
        text = (a.text or "").strip()
        if not text:
            die("草稿正文为空")
        if len(text) > 150:
            die(f"草稿 {len(text)} 字 > 150 字上限")
        if not a.rpid:
            die("需要 --rpid（要回复的那条评论 id）")
        cfg = read_config().get("draft") or {}
        forbid = [w for w in (cfg.get("forbid") or []) if w and w in text]
        if forbid:
            die(f"草稿命中敏感词 {forbid} —— 拒绝入稿")
        # 对方昵称命中疑似 AI 水军关键词（大肥鱼/肥鱼等，config.comment_check.name_keywords）→ 拒入稿
        ck = read_config().get("comment_check") or {}
        name_kw = [w for w in (ck.get("name_keywords") or []) if w]
        if a.from_uname and name_kw and any(k in a.from_uname for k in name_kw):
            hit = [k for k in name_kw if k in a.from_uname]
            die(f"对方昵称 {a.from_uname} 命中疑似 AI 水军关键词 {hit} —— 拒绝入稿（老板 2026-10-27 指示：DeepSeek 水军号不理会）")
        # 同人 30 天限频（2026-10-27 对齐 whale：30 天内不重复打扰同一个人）
        if a.from_uname:
            gap_days = int(cfg.get("reply_interval_days", 30) or 30)
            prev = [r for r in recs if r.get("status") == "sent"
                    and r.get("from") == a.from_uname]
            prev = [r for r in prev if (datetime.now() - datetime.fromisoformat(
                str(r.get("sent_at") or r.get("created_at")))).total_seconds() < gap_days * 86400]
            if prev:
                die(f"同人限频：{gap_days} 天内已回过 {a.from_uname}（{prev[-1].get('sent_at')}）—— 不重复打扰")
        rid = time.strftime("%m%d%H%M%S") + "-" + str(int(time.time() * 1000) % 1000)
        rec = {"id": rid, "bv": a.bv, "rpid": a.rpid, "from": a.from_uname or "",
               "text": text, "status": "pending",
               "created_at": datetime.now().isoformat(timespec="seconds")}
        recs.append(rec)
        save_drafts(recs)
        print(json.dumps({"id": rid, "status": "pending", "bv": a.bv,
                          "reply_to": a.rpid, "from": rec["from"], "text": text,
                          "审批": f"批准：radar.py draft approve {rid} --yes；不要：radar.py draft discard {rid}"},
                         ensure_ascii=False, indent=2))
        return
    if a.action == "list":
        now = datetime.now()
        for r in recs:
            if a.pending and r.get("status") != "pending":
                continue
            age = ""
            try:
                created = datetime.fromisoformat(r["created_at"])
                age = f"{(now - created).total_seconds() / 3600:.1f}h"
            except Exception:  # noqa: BLE001
                pass
            expired = r.get("status") == "pending" and age != "" and float(age.rstrip("h")) > 24
            print(json.dumps({"id": r.get("id"), "status": r.get("status"),
                              "bv": r.get("bv"), "from": r.get("from"),
                              "reply_to": r.get("rpid"), "text": r.get("text"),
                              "age": age, "expired": expired}, ensure_ascii=False))
        return
    if a.action in ("approve", "discard"):
        if not a.id:
            die("需要草稿 id")
        rec = next((r for r in recs if r.get("id") == a.id), None)
        if not rec:
            die(f"没有草稿 {a.id}")
        if rec.get("status") != "pending":
            die(f"草稿 {a.id} 状态是 {rec.get('status')}，不是 pending")
        if a.action == "discard":
            rec["status"] = "discarded"
            save_drafts(recs)
            print(f"已作废 {a.id}")
            return
        # approve：先查过期（24h 未审批自动作废）
        d = state_dir()
        try:
            created = datetime.fromisoformat(rec["created_at"])
            if (datetime.now() - created).total_seconds() > 24 * 3600:
                rec["status"] = "expired"
                save_drafts(recs)
                die(f"草稿 {a.id} 超过 24 小时未审批 → 已自动作废")
        except Exception:  # noqa: BLE001
            pass
        cfg = read_config().get("draft") or {}
        if not cfg.get("enabled", True):
            die("闸①：config.draft.enabled 不是 true —— 拒绝发")
        now = datetime.now()
        sent = [r for r in recs if r.get("status") == "sent"]
        n12 = sum(1 for r in sent
                  if (now - datetime.fromisoformat(str(r.get("sent_at") or r.get("created_at"))))
                  .total_seconds() < 12 * 3600)
        n24 = sum(1 for r in sent
                  if (now - datetime.fromisoformat(str(r.get("sent_at") or r.get("created_at"))))
                  .total_seconds() < 24 * 3600)
        p12 = int(cfg.get("per_12h", 1))
        p24 = int(cfg.get("per_24h", 2))
        if n12 >= p12:
            die(f"闸④：最近 12 小时已发 {n12} 条草稿回复（上限 {p12}）—— 稍后再来")
        if n24 >= p24:
            die(f"闸④：最近 24 小时已发 {n24} 条草稿回复（上限 {p24}）—— 不再发")
        forbid = [w for w in (cfg.get("forbid") or []) if w and w in rec["text"]]
        if forbid:
            die(f"闸②：草稿命中敏感词 {forbid} —— 拒发")
        text = rec["text"]
        if len(text) > 150:
            die(f"闸②：草稿 {len(text)} 字 > 150 字上限")
        cookie = load_cookie()
        jct = csrf_from_cookie(cookie_path().read_text(encoding="utf-8"))
        if not jct:
            die("cookie 里没有 bili_jct（csrf）—— 没法发评论")
        v = get(f"{API}/x/web-interface/view?bvid={rec['bv']}", cookie)["data"]
        if not a.yes:
            print(json.dumps({"id": a.id, "dry_run": True, "bv": rec["bv"],
                              "aid": v["aid"], "reply_to": rec["rpid"], "text": text,
                              "提示": "加 --yes 真发"}, ensure_ascii=False, indent=2))
            return
        _write_cooldown(d, float(read_config().get("write", {}).get("cooldown_sec", 120) or 120))
        res = post_reply(rec["bv"], v["aid"], text, rec["rpid"], cookie, jct)
        if res.get("code") != 0:
            rec["fail_count"] = int(rec.get("fail_count") or 0) + 1
            if rec["fail_count"] >= 3:
                rec["status"] = "failed"
                print(f"⚠️ 草稿 {a.id} 连续 3 次发送失败 → 已标记 failed（等本人看）", file=sys.stderr)
            save_drafts(recs)
            die(f"发回复被拒：code={res.get('code')} msg={res.get('message')}（累计失败 {rec['fail_count']} 次）", 9)
        rpid = (res.get("data") or {}).get("rpid_str") or (res.get("data") or {}).get("rpid")
        rec["status"] = "sent"
        rec["sent_at"] = datetime.now().isoformat(timespec="seconds")
        rec["sent_rpid"] = rpid
        save_drafts(recs)
        print(json.dumps({"id": a.id, "posted": True, "bv": rec["bv"], "rpid": rpid,
                          "text": text}, ensure_ascii=False, indent=2))
        return
    if a.action == "stats":
        from collections import Counter
        print(json.dumps(dict(Counter(r.get("status") for r in recs)),
                         ensure_ascii=False, indent=2))
        return