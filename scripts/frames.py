#!/usr/bin/env python3
"""frames.py — B站视频抽帧看画面（对齐 dsh-bili-whale 的「六路互补」之一）。

用法:
  python3 frames.py --bv BV1xxx [--cid N] [--out DIR] [--strip] [--width 720] [--frames 9]

两种模式:
  默认   均匀抽 N 帧（默认 9 = 3x3 九宫格），每格标注时间戳 → 一张 PNG。
        给模型「看一眼画面」：没字幕的视频也能判断内容/质量。
  --strip  硬字幕模式：拉官方字幕时间轴，在字幕出现的时刻抽帧（20 秒窗口去重，
        最多 --max 帧，默认 18），拼成网格长图 —— 「整片台词一张图读完」。
        适合画面里有硬字幕、但没有字幕轨的视频（剪辑/动画/实拍）。

输出:
  帧图 + 同名 .json（每格 index/时间点/路径）。stdout 打印路径与时间点。
  模型用 image 工具读 PNG；脚本只做确定性的事，判断由模型做。

依赖: ffmpeg + ffprobe（PATH 或环境变量 FFMPEG）。没有 → 报错退出，其余路照常。
"""
import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
API = "https://api.bilibili.com"
REFERER = "https://www.bilibili.com/"

MIX = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
       33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
       26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
       20, 34, 44, 52]

FFMPEG = os.environ.get("FFMPEG") or "ffmpeg"

from mp4_sparse import _SparsePlan, build_sparse, sparse_plan



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
    return Path(__file__).resolve().parents[3] / "interests"


def load_cookie() -> str:
    f = cookie_path()
    if not f.exists():
        die(f"没有 cookie 文件：{f}（先跑 radar.py check 或扫码登录）")
    raw = f.read_text().strip()
    if not raw:
        die("cookie 文件是空的")
    return raw


def http_get_json(url: str, cookie: str, tries: int = 3):
    """GET JSON，指数退避重试（同 radar.py 请求层），风控显式 die。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": REFERER, "Cookie": cookie,
                "Accept": "application/json, text/plain, */*",
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 429:
                time.sleep(min(30 * (i + 1), 120))
            else:
                time.sleep(min(1.5 * (2 ** i), 30.0))
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            time.sleep(min(1.5 * (2 ** i), 30.0))
    die(f"请求失败 {url} → {last}")


def wbi_keys(cookie: str):
    d = http_get_json(f"{API}/x/web-interface/nav", cookie)
    if d.get("code") != 0:
        die(f"nav 失败 code={d.get('code')} msg={d.get('message')}（cookie 可能失效）")
    w = d["data"]["wbi_img"]
    ik = w["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sk = w["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    return "".join((ik + sk)[i] for i in MIX)[:32]


def wbi_sign(params: dict, mix: str) -> str:
    p = dict(params, wts=int(time.time()))
    q = urllib.parse.urlencode(sorted(p.items()))
    return q + "&w_rid=" + hashlib.md5((q + mix).encode()).hexdigest()


def video_info(cookie: str, bv: str, cid: int | None):
    d = http_get_json(f"{API}/x/web-interface/view?bvid={bv}", cookie)
    if d.get("code") != 0:
        die(f"view 失败 code={d.get('code')} msg={d.get('message')}")
    v = d["data"]
    if cid and any(p["cid"] == cid for p in v.get("pages", [])):
        v["cid"] = cid
    return {"bvid": v["bvid"], "aid": v["aid"], "cid": v["cid"],
            "title": v.get("title", ""), "duration": v.get("duration", 0)}


def playurl(cookie: str, bv: str, cid: int, mix: str, start_qn: int = 64):
    """取 durl 直链，qn 从 start_qn→32→16 降级。返回 (url, qn) 或 die。"""
    last = None
    for qn in (start_qn, 32, 16):
        u = (f"{API}/x/player/wbi/playurl?"
             + wbi_sign({"bvid": bv, "cid": cid, "qn": qn, "fnval": 0, "fnver": 0, "fourk": 0}, mix))
        d = http_get_json(u, cookie)
        if d.get("code") != 0:
            last = f"qn={qn} code={d.get('code')} {d.get('message', '')}"
            continue
        durl = (d.get("data") or {}).get("durl") or []
        if durl and durl[0].get("url"):
            url = durl[0]["url"]
            if url.startswith("//"):
                url = "https:" + url
            return url.replace("http://", "https://"), qn
        last = f"qn={qn} 无 durl（可能被限清晰度）"
    die(f"拿不到播放地址（{last}）——可能是会员视频或接口限流")


def subtitles(cookie: str, bv: str, cid: int, mix: str):
    """wbi 签名的 player/v2 拉官方字幕，返回 [{from, to, content}] 或 []。"""
    u = (f"{API}/x/player/wbi/v2?"
         + wbi_sign({"bvid": bv, "cid": cid}, mix))
    d = http_get_json(u, cookie)
    if d.get("code") != 0:
        return []
    subs = (((d.get("data") or {}).get("subtitle") or {}).get("subtitles")) or []
    subs = [s for s in subs if (s.get("subtitle_url") or "").strip()]
    if not subs:
        return []
    pick = next((s for s in subs if str(s.get("lan", "")).startswith("zh")), subs[0])
    su = pick.get("subtitle_url") or ""
    if su.startswith("//"):
        su = "https:" + su
    body = http_get_json(su, cookie)
    return [{"from": b.get("from", 0), "to": b.get("to", 0),
             "content": re.sub(r"\s+", " ", b.get("content", "")).strip()}
            for b in (body.get("body") or []) if b.get("content")]


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def extract_frame(url: str, t: float, w: int, out: Path) -> bool:
    """ffmpeg 在线拉流抽单帧（-ss 在 -i 前快速 seek）。失败（含段错误 rc=139）返回 False。"""
    headers = f"Referer: {REFERER}\r\nUser-Agent: {UA}\r\n"
    cmd = [FFMPEG, "-y", "-headers", headers, "-ss", f"{t:.2f}", "-i", url,
           "-frames:v", "1", "-vf", f"scale={w}:-2", "-q:v", "3", str(out)]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=90)
        return r.returncode == 0 and out.exists() and out.stat().st_size > 0
    except Exception:  # noqa: BLE001
        return False


def extract_frame_local(path: Path, t: float, w: int, out: Path) -> bool:
    """从本地 mp4 抽单帧（无网络，快）。"""
    cmd = [FFMPEG, "-y", "-ss", f"{t:.2f}", "-i", str(path),
           "-frames:v", "1", "-vf", f"scale={w}:-2", "-q:v", "3", str(out)]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=60)
        return r.returncode == 0 and out.exists() and out.stat().st_size > 0
    except Exception:  # noqa: BLE001
        return False


def download_video(url: str, dest: Path) -> bool:
    """Range 并发下载全片到本地（4 段）。当前沙箱 ffmpeg 拉 CDN 流必崩，只能下本地。"""
    import concurrent.futures
    hdr = {"User-Agent": UA, "Referer": REFERER}
    try:
        req = urllib.request.Request(url, headers=dict(hdr, Range="bytes=0-0"))
        with urllib.request.urlopen(req, timeout=20) as r:
            cr = r.headers.get("Content-Range", "")
            total = int(cr.split("/")[-1]) if "/" in cr else 0
        if total <= 0:
            return False
        parts = 4
        seg = total // parts

        def dl(i):
            s = i * seg
            e = (total - 1) if i == parts - 1 else (i + 1) * seg - 1
            q = urllib.request.Request(url, headers=dict(hdr, Range=f"bytes={s}-{e}"))
            with urllib.request.urlopen(q, timeout=120) as r2:
                return r2.read()

        with concurrent.futures.ThreadPoolExecutor(parts) as ex:
            chunks = list(ex.map(dl, range(parts)))
        data = b"".join(chunks)
        if len(data) != total:
            return False
        dest.write_bytes(data)
        return True
    except Exception:  # noqa: BLE001
        return False


def pick_points(dur: float, mode: str, sub_lines, n: int, max_n: int):
    """决定抽帧时间点。默认均匀；strip 按字幕时刻（20 秒窗口去重）。"""
    if mode == "strip":
        pts = []
        for b in sub_lines:
            t = float(b["from"])
            if not pts or t - pts[-1] >= 20:
                pts.append(t)
        return pts[:max_n]
    n = max(1, n)
    return [dur * (i + 0.5) / n for i in range(n)]


def build_grid(imgs: list[Path], times: list[float], w: int, cols: int, title: str):
    """PIL 拼网格：每格 w 宽（16:9 裁切），左下角黑底白字时间戳。"""
    from PIL import Image, ImageDraw, ImageFont
    pad = 6
    title_h = 44
    h_cell = int(w * 9 / 16)
    rows = (len(imgs) + cols - 1) // cols
    W = cols * w + (cols + 1) * pad
    H = rows * h_cell + (rows + 1) * pad + title_h
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=26)
    draw.text((pad + 4, (title_h - 32) // 2), title, fill="black", font=font)
    for i, (im, t) in enumerate(zip(imgs, times)):
        r, c = divmod(i, cols)
        x = pad + c * (w + pad)
        y = title_h + pad + r * (h_cell + pad)
        try:
            pic = Image.open(im).convert("RGB")
        except Exception:  # noqa: BLE001
            pic = Image.new("RGB", (w, h_cell), "gray")
        pic.thumbnail((w, h_cell))
        # 居中 + 裁到格子大小
        pw, ph = pic.size
        if ph < h_cell:
            pic = pic.resize((int(w * ph / h_cell), h_cell)) if ph else pic
        pw, ph = pic.size
        if pw != w or ph != h_cell:
            # 按宽度适配再中心裁高
            scale = w / pw
            pic = pic.resize((w, max(h_cell, int(ph * scale))))
            pw, ph = pic.size
            top = (ph - h_cell) // 2
            pic = pic.crop((0, top, w, top + h_cell))
        canvas.paste(pic, (x, y))
        # 时间戳：黑底白字
        ts = fmt_ts(t)
        tw = draw.textlength(ts, font=font) + 12
        draw.rectangle([x + 6, y + h_cell - 38, x + 6 + tw, y + h_cell - 6], fill="black")
        draw.text((x + 12, y + h_cell - 34), ts, fill="white", font=font)
    return canvas


def main():
    ap = argparse.ArgumentParser(description="B站视频抽帧看画面（九宫格 / 硬字幕长图）")
    ap.add_argument("--bv", required=True, help="BV 号")
    ap.add_argument("--cid", type=int, default=None, help="分P cid（默认第一P）")
    ap.add_argument("--out", default=None, help="输出目录（默认 interests/frames/）")
    ap.add_argument("--strip", action="store_true", help="硬字幕模式：按字幕时刻抽帧")
    ap.add_argument("--width", type=int, default=720, help="每格宽度像素（默认 720）")
    ap.add_argument("--frames", type=int, default=9, help="均匀模式帧数（默认 9）")
    ap.add_argument("--max", dest="max_n", type=int, default=24, help="strip 模式最多帧数（默认 24）")
    a = ap.parse_args()

    if a.frames < 1 or a.max_n < 1:
        die("--frames / --max 至少为 1")
    for exe in (FFMPEG,):
        if subprocess.run([exe, "-version"], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode != 0:
            die(f"找不到 ffmpeg（{exe}）：装进 PATH 或设环境变量 FFMPEG。不装也行——只是少\"看画面\"这一路，字幕/弹幕/热评照常")

    cookie = load_cookie()
    info = video_info(cookie, a.bv, a.cid)
    mix = wbi_keys(cookie)
    url, qn = playurl(cookie, a.bv, info["cid"], mix, start_qn=32 if a.strip else 64)

    sub_lines = []
    if a.strip:
        sub_lines = subtitles(cookie, a.bv, info["cid"], mix)
        if not sub_lines:
            die(f"{a.bv} 没有官方字幕轨 —— strip 模式需要字幕时间轴（没有字幕轨但有硬字幕时，先手动给时间轴）")

    pts = pick_points(info["duration"], "strip" if a.strip else "grid",
                      sub_lines, a.frames, a.max_n)

    out_dir = Path(a.out) if a.out else state_dir() / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{a.bv}" + (f"-c{a.cid}" if a.cid and a.cid != info["cid"] else "")
    tmp = out_dir / f".{tag}.tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    imgs, ok_times = [], []
    local_path = None

    # 第一帧先试在线拉流；失败 → 稀疏下载（只拉 moov+GOP 段）→ 再不行全片下载
    first = tmp / "f00.jpg"
    if extract_frame(url, pts[0], a.width, first):
        imgs.append(first)
        ok_times.append(pts[0])
    else:
        # 拿资源总大小
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER, "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                total = int(r.headers.get("Content-Range", "").split("/")[-1])
        except Exception:  # noqa: BLE001
            total = 0
        local_path = out_dir / f".{tag}.mp4"
        plan = sparse_plan(url, total, pts) if total > 0 else None
        if plan is not None and build_sparse(url, total, plan.ranges(pts), local_path):
            dl = sum(e - s + 1 for s, e in plan.ranges(pts))
            print(f"[降级] 在线拉流失败 → 稀疏下载（只拉 moov+采样点 GOP：下载 {dl/1048576:.1f}MB，全片 {total/1048576:.0f}MB）→ 本地抽帧", file=sys.stderr)
        elif download_video(url, local_path):
            print("[降级] 稀疏方案不可用（非 faststart？）→ 整片下载后本地抽帧", file=sys.stderr)
        else:
            die("在线拉流/稀疏/整片下载都失败——本轮跳过画面路，其余照常")
    for i, t in enumerate(pts):
        if i == 0 and imgs:
            continue
        f = tmp / f"f{i:02d}.jpg"
        ok = extract_frame_local(local_path, t, a.width, f) if local_path \
            else extract_frame(url, t, a.width, f)
        if ok:
            imgs.append(f)
            ok_times.append(t)
    if local_path is not None:
        try:
            local_path.unlink()
        except OSError:
            pass
    if not imgs:
        die("抽帧全部失败（播放地址失效/网络问题）——本轮跳过画面路，其余照常")

    cols = 3 if len(imgs) > 4 else 1
    if a.strip:
        cols = 3
    title = f"{a.bv}  dur={info['duration']}s  qn={qn}  {len(imgs)}f"
    canvas = build_grid(imgs, ok_times, a.width, cols, title)
    png = out_dir / f"frames_{tag}.png"
    canvas.save(png, quality=90)
    meta = {"bvid": a.bv, "cid": info["cid"], "title": info["title"],
            "duration": info["duration"], "qn": qn, "mode": "strip" if a.strip else "grid",
            "grid": f"{cols}x{(len(imgs) + cols - 1) // cols}", "frames": len(imgs),
            "width": a.width, "image": str(png),
            "points": [{"index": i, "t": round(t, 2), "ts": fmt_ts(t)}
                       for i, t in enumerate(ok_times)]}
    (out_dir / f"frames_{tag}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    for f in imgs:
        try:
            f.unlink()
        except OSError:
            pass
    print(f"OK {png}")
    print(f"title={info['title']}  dur={info['duration']}s  帧数={len(imgs)}  每格宽={a.width}  清晰度qn={qn}")
    print("时间点: " + " ".join(f"[{fmt_ts(t)}]" for t in ok_times))
    print(f"JSON: {out_dir / f'frames_{tag}.json'}")


if __name__ == "__main__":
    main()