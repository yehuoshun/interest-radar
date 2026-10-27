#!/usr/bin/env python3
"""B站扫码登录：生成二维码 → 轮询确认 → 更新 cookie 文件"""
import re, sys, time, json
from urllib.parse import urlparse, parse_qs

import requests
import qrcode

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
})
COOKIE_FILE = "/home/admin/.openclaw/secrets/bilibili-cookies.txt"
QR_PATH = f"/home/admin/.openclaw/workspace/tmp/bili-qr-login-{int(time.time())}.png"


def log(msg):
    print(msg, flush=True)


# 1) 生成二维码
r = S.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate", timeout=10)
j = r.json()
if j.get("code") != 0:
    log(f"GENERATE_FAIL {j}")
    sys.exit(1)
url = j["data"]["url"]
key = j["data"]["qrcode_key"]
log(f"QR_KEY {key}")

img = qrcode.make(url)
img.save(QR_PATH)
log(f"QR_SAVED {QR_PATH}")

# 2) 轮询确认
deadline = time.time() + 180
last_code = None
while time.time() < deadline:
    time.sleep(2)
    try:
        r = S.get("https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                  params={"qrcode_key": key}, timeout=10)
        j = r.json()
    except Exception as e:
        log(f"POLL_ERR {e}")
        continue
    code = j.get("code")
    d = j.get("data") or {}
    dcode = d.get("code")
    if code != 0:
        log(f"POLL_HTTP_FAIL {j}")
        break
    if dcode == -2:
        if last_code != -2:
            log("WAIT_SCAN")
            last_code = -2
    elif dcode == -4:
        if last_code != -4:
            log("SCANNED_CONFIRM_PENDING")
            last_code = -4
    elif dcode == 0:
        log("CONFIRMED")
        u = d.get("url", "")
        # 跟随 crossDomain 跳转，从 Set-Cookie 拿登录态
        r2 = S.get(u, timeout=15, allow_redirects=True)
        log(f"CROSS_STATUS {r2.status_code} final={r2.url[:100]}")
        cj = requests.utils.dict_from_cookiejar(S.cookies)
        sess = cj.get("SESSDATA", "")
        jct = cj.get("bili_jct", "")
        dede = cj.get("DedeUserID", "")
        md5 = cj.get("DedeUserID__ckMd5", "")
        if not sess or not jct or not dede:
            # 兜底：解析 gourl 参数里的 SESSDATA
            qs0 = parse_qs(urlparse(u).query)
            gourl = qs0.get("gourl", [""])[0]
            if gourl:
                gq = parse_qs(urlparse(gourl).query)
                sess = sess or gq.get("SESSDATA", [""])[0]
                jct = jct or gq.get("bili_jct", [""])[0]
                dede = dede or gq.get("DedeUserID", [""])[0]
                md5 = md5 or gq.get("DedeUserID__ckMd5", [""])[0]
        if not sess or not jct or not dede:
            log(f"PARSE_FAIL url={u[:120]}")
            sys.exit(1)
        # 3) 更新 cookie 文件（保留 buvid3 等设备字段，替换认证四件）
        old = open(COOKIE_FILE, encoding="utf-8").read().strip()
        # 备份
        with open(COOKIE_FILE + ".bak-qr", "w", encoding="utf-8") as f:
            f.write(old + "\n")
        repl = {
            r"SESSDATA=[^;]*": f"SESSDATA={sess}",
            r"bili_jct=[^;]*": f"bili_jct={jct}",
            r"DedeUserID=[^;]*": f"DedeUserID={dede}",
            r"DedeUserID__ckMd5=[^;]*": f"DedeUserID__ckMd5={md5}",
        }
        new = old
        for pat, val in repl.items():
            if re.search(pat, new):
                new = re.sub(pat, val, new)
            else:
                new = new + "; " + val
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write(new + "\n")
        log("LOGIN_OK")
        sys.exit(0)
    elif dcode == -5:
        log("QR_EXPIRED")
        sys.exit(2)
    else:
        log(f"UNKNOWN_DCODE {dcode}")
        time.sleep(2)

log("POLL_TIMEOUT")
sys.exit(3)
