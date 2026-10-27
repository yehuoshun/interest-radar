#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar.py —— 兴趣雷达入口：argparse 路由 + 全量 re-export（兼容测试与旧调用方）。

模块结构（scripts/）：
  core.py        基础设施：常量/路径/cookie/配置/die
  bili_client.py B站请求层：退避/熔断/wbi/csrf/GET+POST
  gates.py       写操作闸：冷却/频控/失败关闸/账本
  browse.py      浏览域：check/搜索/字幕/seen
  comment.py     评论域：@主号/自发评论/快筛/可见性
  draft.py       草稿审核状态机
  notify.py      通知与私信（dm 水位 / msg 白名单）
  dynamic.py     动态发/删
  feedback.py    反馈记账/统计/活跃度
  frames.py      抽帧看画面（含 mp4_sparse 稀疏下载）
  tests/         unittest（35 用例，零网络）
"""
import argparse

# ── 基础设施 & 请求层 ──────────────────────────────────────────
from radar_lib.client import (_BACKOFF, _note_fail, _note_ok, _retry_sleep, csrf_from_cookie,
                         get, post_form, post_json, wbi_keys, wbi_sign)
from radar_lib.core import API, UA, clean, cookie_path, die, load_cookie, read_config, state_dir

# ── 写操作闸 ───────────────────────────────────────────────────
from radar_lib.gates import (_ago_h, _record_write, _write_cooldown, _write_fail, _write_gate,
                   mention_log, note_failure, write_log)

# ── 域模块 ─────────────────────────────────────────────────────
from radar_lib.browse import cmd_check, cmd_search, cmd_seen, cmd_sub, fetch_subtitle_text
from radar_lib.comment import (anon_get, cmd_check_reply, cmd_comment, cmd_comment_check,
                     cmd_rate, cmd_reply, fetch_hot_comments, post_reply, visible_anon)
from radar_lib.draft import cmd_draft, drafts_file, load_drafts, save_drafts
from radar_lib.dynamic import cmd_dynamic, cmd_dynamic_del
from radar_lib.feedback import cmd_engagement, cmd_feedback, cmd_stats
from radar_lib.notify import cmd_dm, cmd_msg, cmd_notify, radar_unread


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
    s.add_argument("--reply-to", dest="reply_to", help="楼中楼：回复某条评论的 rpid（带上 root/parent）")
    s.add_argument("--yes", action="store_true", help="真正发出（默认干跑，只打印会发什么）")
    s.set_defaults(fn=cmd_reply)

    s = sub.add_parser("check-reply")
    s.add_argument("--bv", required=True)
    s.add_argument("--rpid", required=True)
    s.set_defaults(fn=cmd_check_reply)

    s = sub.add_parser("rate")
    s.add_argument("--per-round", dest="per_round", type=int)
    s.add_argument("--per-hour", dest="per_hour", type=int)
    s.add_argument("--per-day", dest="per_day", type=int)
    s.set_defaults(fn=cmd_rate)

    s = sub.add_parser("feedback")
    s.add_argument("--topic", required=True)
    s.add_argument("--signal", required=True, choices=["like", "skip", "note"],
                   help="like=有用 / skip=没用 / note=只留证据不动权重")
    s.add_argument("--bv")
    s.add_argument("--score", type=int)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_feedback)

    s = sub.add_parser("draft")
    s.add_argument("action", choices=["new", "list", "approve", "discard", "stats"])
    s.add_argument("--bv")
    s.add_argument("--rpid", help="要回复的那条评论 id")
    s.add_argument("--from", dest="from_uname", help="对方昵称（记草稿用）")
    s.add_argument("--text")
    s.add_argument("--pending", action="store_true", help="list 只列待审")
    s.add_argument("--yes", action="store_true", help="approve 真发（默认干跑）")
    s.add_argument("id", nargs="?")
    s.set_defaults(fn=cmd_draft)

    s = sub.add_parser("comment-check")
    s.add_argument("--bv", required=True)
    s.add_argument("--num", type=int, default=0, help="拉多少条热评（默认 config.comment_check.num）")
    s.set_defaults(fn=cmd_comment_check)

    s = sub.add_parser("comment")
    s.add_argument("--bv", required=True)
    s.add_argument("--text", required=True, help="自发评论正文（≤200 字，无需 @ 主号）")
    s.add_argument("--yes", action="store_true", help="真正发出（默认干跑）")
    s.set_defaults(fn=cmd_comment)

    s = sub.add_parser("dynamic")
    s.add_argument("--text", required=True, help="动态正文（≤200 字）")
    s.add_argument("--yes", action="store_true", help="真正发出（默认干跑）")
    s.set_defaults(fn=cmd_dynamic)

    s = sub.add_parser("dynamic-del")
    s.add_argument("--dyn-id", dest="dyn_id", required=True, help="要删的动态 id（dyn_id_str）")
    s.add_argument("--yes", action="store_true", help="真正删除（默认干跑）")
    s.set_defaults(fn=cmd_dynamic_del)

    s = sub.add_parser("msg")
    s.add_argument("--mid", required=True, help="收件人 uid（必须在 config.write.message.allow_mid 白名单里）")
    s.add_argument("--text", required=True, help="私信正文（≤200 字）")
    s.add_argument("--yes", action="store_true", help="真正发出（默认干跑）")
    s.set_defaults(fn=cmd_msg)

    s = sub.add_parser("dm")
    s.add_argument("--mid", help="对方 mid（默认 config.json 的 mention.mid = 主号）")
    s.add_argument("--size", type=int, default=20, help="拉多少条（默认 20）")
    s.add_argument("--new-only", dest="new_only", action="store_true",
                   help="只列时间水位之后的新消息")
    s.set_defaults(fn=cmd_dm)

    s = sub.add_parser("notify")
    s.add_argument("--new-only", dest="new_only", action="store_true",
                   help="只列比上次新的（用时间水位，不靠未读计数）")
    s.set_defaults(fn=cmd_notify)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)

    s = sub.add_parser("engagement")
    s.add_argument("--days", type=int, default=14, help="统计窗口（默认 14 天）")
    s.set_defaults(fn=cmd_engagement)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

# 兼容：旧脚本/测试直接 import radar 时拿到的符号集合 = 上面全部 re-export。
# 需要更多符号（如 datetime）时请在对应域模块里 import，不要往这里塞。