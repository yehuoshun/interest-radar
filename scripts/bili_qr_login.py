#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B站扫码登录：生成二维码 → 轮询确认 → 更新 cookie 文件。

    python scripts/bili_qr_login.py

跨平台版（2026-11-13）：cookie 路径走 `bili_radar.core.cookie_path()`，
二维码临时图落在 `<state>/tmp/qr-<ts>.png`（不再写死 /home/admin/…），
HTTP 全用标准库 urllib（原版依赖 requests，本机没装）。

唯一可选依赖：`qrcode`（渲染二维码 PNG）。没装就只打印登录 URL 并退出，
提示 `python -m pip install "qrcode[pil]"`。轮询/写回 cookie 的部分不需要它。

状态码（打印在 stdout，给 agent 解析）：
    QR_KEY <key>            已取到二维码
    QR_SAVED <path>         二维码 PNG 路径
    WAIT_SCAN               等待扫码
    SCANNED_CONFIRM_PENDING 已扫待确认
    LOGIN_OK                cookie 已更新（旧文件备份成 .bak-qr）
    QR_EXPIRED              二维码过期，重跑
    POLL_TIMEOUT / PARSE_FAIL / GENERATE_FAIL / MISSING_DEP
退出码：0 成功 · 1 生成/解析失败 · 2 过期 · 3 超时 · 4 缺 qrcode
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bili_radar.core import cookie_path, die, ensure_state_dir, repo_root  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


def log(msg):
    print(msg, flush=True)


def http_json(url, timeout=15):
    req = urllib.request.Request(url, headers=HDRS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def follow(url, timeout=15):
    """跟随 crossDomain 跳转，返回 (status, final_url, cookiejar)。"""
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(url, headers=HDRS)
    with opener.open(req, timeout=timeout) as r:
        return r.status, r.geturl(), jar


def cookies_dict(jar):
    return {c.name: c.value for c in jar}


def main():
    # 1) 生成二维码
    try:
        j = http_json(GENERATE)
    except Exception as e:  # noqa: BLE001
        log(f"GENERATE_FAIL {e}")
        sys.exit(1)
    if j.get("code") != 0:
        log(f"GENERATE_FAIL {j}")
        sys.exit(1)
    url = j["data"]["url"]
    key = j["data"]["qrcode_key"]
    log(f"QR_KEY {key}")

    try:
        import qrcode  # noqa: PLC0415
    except ImportError:
        log("MISSING_DEP qrcode")
        log(f"QR_URL {url}")
        log('装依赖后重跑：python -m pip install "qrcode[pil]"')
        sys.exit(4)
    qr_dir = ensure_state_dir() / "tmp"
    qr_dir.mkdir(parents=True, exist_ok=True)
    qr_path = qr_dir / f"qr-{int(time.time())}.png"
    qrcode.make(url).save(qr_path)
    log(f"QR_SAVED {qr_path}")

    # 2) 轮询确认（180s）
    deadline = time.time() + 180
    last = None
    while time.time() < deadline:
        time.sleep(2)
        try:
            j = http_json(f"{POLL}?qrcode_key={urllib.parse.quote(key)}")
        except Exception as e:  # noqa: BLE001
            log(f"POLL_ERR {e}")
            continue
        if j.get("code") != 0:
            log(f"POLL_HTTP_FAIL {j}")
            break
        d = j.get("data") or {}
        dcode = d.get("code")
        if dcode == -2:
            if last != -2:
                log("WAIT_SCAN")
                last = -2
        elif dcode == -4:
            if last != -4:
                log("SCANNED_CONFIRM_PENDING")
                last = -4
        elif dcode == 0:
            log("CONFIRMED")
            target = d.get("url", "")
            try:
                status, final, jar = follow(target)
                log(f"CROSS_STATUS {status} final={final[:100]}")
            except Exception as e:  # noqa: BLE001
                log(f"CROSS_ERR {e}")
                jar, final = None, ""
            cj = cookies_dict(jar) if jar is not None else {}
            sess = cj.get("SESSDATA", "")
            jct = cj.get("bili_jct", "")
            dede = cj.get("DedeUserID", "")
            md5 = cj.get("DedeUserID__ckMd5", "")
            if not sess or not jct or not dede:
                # 兜底：解析 gourl 里的 SESSDATA
                gq = urllib.parse.parse_qs(
                    urllib.parse.parse_qs(urllib.parse.urlparse(target).query).get("gourl", [""])[0]
                )
                sess = sess or gq.get("SESSDATA", [""])[0]
                jct = jct or gq.get("bili_jct", [""])[0]
                dede = dede or gq.get("DedeUserID", [""])[0]
                md5 = md5 or gq.get("DedeUserID__ckMd5", [""])[0]
            write_cookie(sess, jct, dede, md5)
            return
        elif dcode == -5:
            log("QR_EXPIRED")
            sys.exit(2)
        else:
            log(f"UNKNOWN_DCODE {dcode}")
    log("POLL_TIMEOUT")
    sys.exit(3)


def write_cookie(sess, jct, dede, md5):
    """把四个认证字段写回 cookie 文件（保留 buvid3 等设备字段），旧文件备份 .bak-qr。"""
    f = cookie_path()
    if not sess or not jct or not dede:
        log(f"PARSE_FAIL 没拿到登录态（path={f}）")
        sys.exit(1)
    old = f.read_text(encoding="utf-8").strip() if f.is_file() else ""
    if old:
        f.with_name(f.name + ".bak-qr").write_text(old + "\n", encoding="utf-8")
    repl = {
        r"SESSDATA=[^;]*": f"SESSDATA={sess}",
        r"bili_jct=[^;]*": f"bili_jct={jct}",
        r"DedeUserID=[^;]*": f"DedeUserID={dede}",
        r"DedeUserID__ckMd5=[^;]*": f"DedeUserID__ckMd5={md5}",
    }
    new = old
    for pat, val in repl.items():
        new = re.sub(pat, val, new) if re.search(pat, new) else (new + "; " + val).lstrip("; ")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(new + "\n", encoding="utf-8")
    log(f"COOKIE_FILE {f}")
    log("LOGIN_OK")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        die("已中断", 130)
