#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core.py —— 基础设施：常量 / 路径 / cookie / 配置 / 通用工具。

零依赖（不 import 本包其他模块），给所有域模块用。
"""
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
API = "https://api.bilibili.com"


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
    # 向上找 <workspace>/skills/interest-radar 标记，不依赖文件层级深度
    # （2026-10-27 包化后加了 bili_radar/ 一层，原来的 parents[3] 会算到 skills/interests）
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "skills" / "interest-radar").is_dir():
            return parent / "interests"
    # 兜底：裸 checkout（CI 就是这种，没有 skills/ 层）
    # scripts/bili_radar/core.py → parents[1]=scripts → .parent=仓库根
    # （原来是 parents[3]，包化后深了一层，会多跳一级到 <work>/interests —— 2026-10-27 CI 抓到）
    return here.parents[1].parent / "interests"


def load_cookie() -> str:
    f = cookie_path()
    if not f.exists():
        die(f"没有 cookie 文件：{f}（读字幕必须登录）")
    raw = f.read_text(encoding="utf-8").strip()
    if "=" not in raw:
        die(f"cookie 文件格式不对：{f}")
    return "; ".join(l.strip().rstrip(";") for l in raw.splitlines() if l.strip())


def read_config():
    f = state_dir() / "config.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def clean(s: str) -> str:
    return urllib.parse.unquote(re.sub(r"<[^>]+>", "", s or "")).strip()