#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core.py —— 基础设施：常量 / 路径 / cookie / 配置 / 通用工具。

零依赖（不 import 本包其他模块），给所有域模块用。

路径口径（2026-11-13 改成跨平台 / DSH 版，Windows 与 Linux 同一套逻辑）：

    REPO_ROOT          仓库根 = scripts/bili_radar/core.py 往上三级
    状态目录           $INTERESTS_DIR，否则 <REPO_ROOT>/state
                      （profile.md / charter.md / config.json / out/ / frames/ 全在这里）
    cookie             $BILI_COOKIE_FILE，否则按顺序取第一个存在的候选：
                       ① <工作区根>/config/bilibili_cookies.txt   ← 工作区约定：凭据只放 config/
                       ② <REPO_ROOT>/config/bilibili_cookies.txt   ← 项目内独立部署时用
                       ③ ~/.openclaw/secrets/bilibili-cookies.txt  ← 旧 OpenClaw 布局，只做兼容读取
                       都不存在时按 ① 报错（错误信息里给出这个路径）
    工作区根           <REPO_ROOT>/../.. 当且仅当 REPO_ROOT 的父目录叫 code；
                      否则视为“裸 checkout”，工作区根 = REPO_ROOT

原来写死的是 `~/.openclaw/workspace/interests`（状态）和
`~/.openclaw/secrets/bilibili-cookies.txt`（cookie），并靠向上找 `skills/interest-radar`
标记定位 —— 那是 OpenClaw 的安装布局，本机 Windows/DSH 环境里两者都不存在。
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

# scripts/bili_radar/core.py → parents[0]=bili_radar, [1]=scripts, [2]=仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]

COOKIE_NAME = "bilibili_cookies.txt"
LEGACY_COOKIE = Path.home() / ".openclaw" / "secrets" / "bilibili-cookies.txt"


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def repo_root() -> Path:
    return REPO_ROOT


def workspace_root() -> Path:
    """工作区根：<workspace>/code/<项目> 布局下就是往上两级，否则退回仓库根。"""
    parent = REPO_ROOT.parent
    if parent.name.lower() == "code":
        return parent.parent
    return REPO_ROOT


def state_dir() -> Path:
    p = os.environ.get("INTERESTS_DIR")
    if p:
        return Path(p).expanduser()
    return REPO_ROOT / "state"


def ensure_state_dir() -> Path:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def cookie_candidates() -> list:
    """候选 cookie 路径，按优先级排列（第一个存在的被采用）。"""
    return [
        workspace_root() / "config" / COOKIE_NAME,
        REPO_ROOT / "config" / COOKIE_NAME,
        LEGACY_COOKIE,
    ]


def cookie_path() -> Path:
    p = os.environ.get("BILI_COOKIE_FILE")
    if p:
        return Path(p).expanduser()
    for cand in cookie_candidates():
        if cand.is_file():
            return cand
    return workspace_root() / "config" / COOKIE_NAME


def load_cookie() -> str:
    f = cookie_path()
    if not f.exists():
        die(f"没有 cookie 文件：{f}\n"
            f"      这一行是 B站登录态（SESSDATA=…; bili_jct=…; DedeUserID=…），读字幕/评论必须有它。\n"
            f"      放法：把浏览器里小号的 cookie 存成一行文本写进上面这个路径（别提交进仓库）。")
    raw = f.read_text(encoding="utf-8").strip()
    if "=" not in raw:
        die(f"cookie 文件格式不对：{f}（应是一行或多行 `k=v; k=v`）")
    return "; ".join(l.strip().rstrip(";") for l in raw.splitlines() if l.strip())


def read_config():
    f = state_dir() / "config.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def clean(s: str) -> str:
    return urllib.parse.unquote(re.sub(r"<[^>]+>", "", s or "")).strip()
