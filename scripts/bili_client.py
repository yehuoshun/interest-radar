#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bili_client.py —— B站 API 请求层：指数退避 / 熔断 / wbi 签名 / csrf / GET+POST。

依赖 core（UA/API/die）。域模块（browse/comment/draft/notify/dynamic/feedback）
统一从这里拿请求能力，不要直接 import urllib。
"""
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from core import API, UA, die

# wbi 签名用的混淆表（B站前端同款）
MIX = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
       33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
       26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
       20, 34, 44, 52]

# 请求层退避状态（2026-10-27 对齐 dsh-bili-whale：指数退避 + 熔断）
_BACKOFF = {"streak": 0}


def _retry_sleep(i: int) -> None:
    """指数退避：1.5 → 3 → 6 → 12 → 24 → 48 → 60s（cap 60s）。"""
    time.sleep(min(1.5 * (2 ** i), 60.0))


def _note_ok() -> None:
    _BACKOFF["streak"] = 0


def _note_fail(kind: str, why: str) -> None:
    _BACKOFF["streak"] += 1
    if _BACKOFF["streak"] >= 3:
        die(f"连续 {_BACKOFF['streak']} 次请求失败（{kind}: {why}）——疑似风控或网络恶化，本轮熔断停止", 3)


def get(url: str, cookie: str, tries: int = 3):
    """带 UA/Referer/Cookie 的 GET，返回 json。

    退避（2026-10-27 对齐 whale）：网络抖动 → 指数退避重试；
    429 → 尊重 Retry-After（最多等 5 分钟）；风控（-412/v_voucher）→ 立即停；
    业务 code≠0 → 不重试直接报错（重试无用）；连续 3 次失败 → 熔断本轮。
    """
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
                _note_ok()
                return data
            code = data.get("code")
            if code == 0:
                _note_ok()
                return data
            if code == -412:
                die("被风控（-412）：换 IP 或稍后再试（沙箱出口是阿里云段，容易踩）", 2)
            msg = str(data.get("message") or "")
            if "v_voucher" in json.dumps(data.get("data") or {}, ensure_ascii=False) or "风控" in msg:
                die("被风控（v_voucher）：需要干净的出口 IP 或过验证", 2)
            die(f"接口错误 {url} → code={code} msg={msg}", 4)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 429:
                ra = e.headers.get("Retry-After", "")
                wait = min(int(ra) if ra.isdigit() else 30 * (i + 1), 300)
                print(f"[退避] 429 限流：等 {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                _retry_sleep(i)
            _note_fail("网络/HTTP", last)
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            _retry_sleep(i)
            _note_fail("网络", last)
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


def csrf_from_cookie(raw: str) -> str:
    m = re.search(r"bili_jct=([^;\s]+)", raw)
    return m.group(1) if m else ""


def post_json(url: str, body: dict, cookie: str, referer: str, tries: int = 2):
    """JSON body 的 POST（发动态用这个，form 编码会 -400）。**有副作用**。

    退避同 get()：网络异常指数退避，429 尊重 Retry-After，连续失败熔断。
    """
    data = json.dumps(body, ensure_ascii=False).encode()
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, data=data, headers={
            "User-Agent": UA, "Referer": referer, "Cookie": cookie,
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                _note_ok()
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 429:
                ra = e.headers.get("Retry-After", "")
                wait = min(int(ra) if ra.isdigit() else 30 * (i + 1), 300)
                print(f"[退避] 429 限流：等 {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                _retry_sleep(i)
            _note_fail("网络/HTTP", last)
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            _retry_sleep(i)
            _note_fail("网络", last)
    die(f"POST(JSON) 失败：{url} → {last}", 8)


def post_form(url: str, fields: dict, cookie: str, referer: str, tries: int = 2):
    """带 csrf 的表单 POST，返回 json。**有副作用**，只给写操作调用。

    退避同 get()：网络异常指数退避，429 尊重 Retry-After，连续失败熔断。
    """
    body = urllib.parse.urlencode(fields).encode()
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, data=body, headers={
            "User-Agent": UA, "Referer": referer, "Cookie": cookie,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                _note_ok()
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 429:
                ra = e.headers.get("Retry-After", "")
                wait = min(int(ra) if ra.isdigit() else 30 * (i + 1), 300)
                print(f"[退避] 429 限流：等 {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                _retry_sleep(i)
            _note_fail("网络/HTTP", last)
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            _retry_sleep(i)
            _note_fail("网络", last)
    die(f"POST 失败：{url} → {last}", 8)