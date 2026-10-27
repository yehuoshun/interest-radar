#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mp4_sparse.py —— 稀疏下载（2026-10-27）：只拉 moov + 每个采样点的 GOP 段。

实测：全片 26MB → 242KB/帧段，抽帧结果与全片逐字节一致。
ffmpeg 对稀疏 mp4 的 seek 由 moov 索引驱动 —— mdat 缺口（零填充）不影响精确抽帧。
"""
import struct
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
REFERER = "https://www.bilibili.com/"

# ── 稀疏下载（2026-10-27）：只拉 moov + 每个采样点的 GOP 段，零填充其余 → ffmpeg 精确 seek
#    实测：全片 26MB → 242KB/9 帧，抽帧结果与全片逐字节一致。


def _fetch_range(url: str, start: int, end: int, timeout: int = 60) -> bytes:
    """Range 下载 [start, end]（闭区间）。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER,
                                                "Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _parse_boxes(data: bytes, base: int, end: int):
    """迭代 box 列表 [(abs_off, size, type)]。"""
    out = []
    i = 0
    while i + 8 <= end - base:
        sz, ty = struct.unpack(">I4s", data[base + i:base + i + 8])
        ty = ty.decode("latin1")
        hdr = 8
        if sz == 1:
            sz = struct.unpack(">Q", data[base + i + 8:base + i + 16])[0]
            hdr = 16
        elif sz == 0:
            sz = end - base - i
        if sz < 8:
            break
        out.append((base + i, sz, ty))
        i += sz
    return out


_CONTAINERS = {"moov", "trak", "mdia", "minf", "stbl", "edts", "dinf"}


def _find_box(data: bytes, off: int, size: int, want: str, depth: int = 0):
    out = []
    for ko, ks, kt in _parse_boxes(data, off + 8, off + size):
        if kt == want:
            out.append((ko, ks))
        if kt in _CONTAINERS and depth < 8:
            out += _find_box(data, ko, ks, want, depth + 1)
    return out


def _table(data: bytes, stbl_off: int, stbl_size: int, typ: str):
    off, size = _find_box(data, stbl_off, stbl_size, typ)[0]
    raw = data[off + 8:off + size]
    if typ == "stsz":
        ss = struct.unpack(">I", raw[4:8])[0]
        cnt = struct.unpack(">I", raw[8:12])[0]
        if ss:
            return [ss] * cnt
        return [struct.unpack(">I", raw[12 + i * 4:16 + i * 4])[0] for i in range(cnt)]
    cnt = struct.unpack(">I", raw[4:8])[0]
    if typ == "stts":
        return [struct.unpack(">I", raw[8 + i * 4:12 + i * 4])[0] for i in range(cnt * 2)]
    if typ == "stsc":
        return [struct.unpack(">I", raw[8 + i * 4:12 + i * 4])[0] for i in range(cnt * 3)]
    return [struct.unpack(">I", raw[8 + i * 4:12 + i * 4])[0] for i in range(cnt)]


class _SparsePlan:
    """解析 moov，把采样时刻映射为需要下载的字节区间。仅 faststart（moov 在头）。"""

    def __init__(self, zone: bytes, moov_off: int, moov_size: int, stbl_off: int,
                 timescale: int, stts, stss, stsc, stsz, stco, moov_end: int):
        self.zone = zone
        self.moov_end = moov_end
        self.timescale = timescale
        self.stts, self.stss, self.stsc, self.stsz, self.stco = stts, stss, stsc, stsz, stco

    def _sample_chunk(self, idx: int):
        acc = 0
        for k in range(len(self.stsc) // 3):
            first = self.stsc[k * 3]
            spc = self.stsc[k * 3 + 1]
            nxt = self.stsc[(k + 1) * 3] if k + 1 < len(self.stsc) // 3 else len(self.stco) + 1
            span = (nxt - first) * spc
            if idx < acc + span:
                rel = idx - acc
                return first - 1 + rel // spc, rel % spc
            acc += span
        return 0, 0

    def _sample_offset(self, idx: int):
        ch, rel = self._sample_chunk(idx)
        # 找 ch（0-based）所在的 stsc entry，算该 chunk 的起始 sample 序号
        acc_samples = 0
        start = 0
        for k in range(len(self.stsc) // 3):
            first = self.stsc[k * 3]
            spc = self.stsc[k * 3 + 1]
            nxt = self.stsc[(k + 1) * 3] if k + 1 < len(self.stsc) // 3 else len(self.stco) + 1
            if first - 1 <= ch < nxt - 1:
                start = acc_samples + (ch - (first - 1)) * spc
                break
            acc_samples += (nxt - first) * spc
        off_in = sum(self.stsz[start:start + rel])
        return self.stco[ch] + off_in, self.stsz[start + rel]

    def ranges(self, times: list[float], pad: int = 65536):
        """采样时间 → [(start, end)] 下载区间（含 moov 区）。"""
        segs = [(0, self.moov_end)]
        for t in times:
            tt = int(t * self.timescale)
            acc, base, idx = 0, 0, 0
            for k in range(len(self.stts) // 2):
                cnt, delta = self.stts[k * 2], self.stts[k * 2 + 1]
                if acc + cnt * delta >= tt:
                    idx = base + min(cnt - 1, (tt - acc) // delta)
                    break
                acc += cnt * delta
                base += cnt
            kf = max([k for k in self.stss if k <= idx + 1], default=self.stss[0])
            k_off, _ = self._sample_offset(kf - 1)
            t_off, t_sz = self._sample_offset(idx)
            segs.append((k_off, t_off + t_sz + pad))
        # 合并重叠区间
        segs.sort()
        merged = []
        for s, e in segs:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        return merged


def sparse_plan(url: str, total: int, times: list[float]):
    """解析 moov 返回 _SparsePlan；非 faststart 或解析失败返回 None。"""
    try:
        head = _fetch_range(url, 0, 131071)
        ftyp_size = struct.unpack(">I", head[:4])[0]
        if 0 < ftyp_size < 131071 and head[ftyp_size + 4:ftyp_size + 8] == b"moov":
            moov_off = ftyp_size
        else:
            return None
        moov_size = struct.unpack(">I", head[moov_off:moov_off + 4])[0]
        moov_end = moov_off + moov_size
        zone = _fetch_range(url, 0, moov_end - 1)
        video_trak = None
        for trak_off, trak_size in _find_box(zone, moov_off, moov_size, "trak"):
            for h in _find_box(zone, trak_off, trak_size, "hdlr"):
                if zone[h[0] + 16:h[0] + 20] == b"vide":
                    video_trak = (trak_off, trak_size)
                    break
            if video_trak:
                break
        if not video_trak:
            return None
        stbl_off, stbl_size = _find_box(zone, video_trak[0], video_trak[1], "stbl")[0]
        mdhd = _find_box(zone, video_trak[0], video_trak[1], "mdhd")[0]
        timescale = struct.unpack(">I", zone[mdhd[0] + 20:mdhd[0] + 24])[0]
        if timescale <= 0:
            return None
        plan = _SparsePlan(zone, moov_off, moov_size, stbl_off, timescale,
                           _table(zone, stbl_off, stbl_size, "stts"),
                           _table(zone, stbl_off, stbl_size, "stss"),
                           _table(zone, stbl_off, stbl_size, "stsc"),
                           _table(zone, stbl_off, stbl_size, "stsz"),
                           _table(zone, stbl_off, stbl_size, "stco"),
                           moov_end)
        return plan
    except Exception:  # noqa: BLE001
        return None


def build_sparse(url: str, total: int, ranges, dest: Path) -> bool:
    """并发下载区间，零填充其余，稀疏写盘。"""
    import concurrent.futures
    try:
        with concurrent.futures.ThreadPoolExecutor(min(6, len(ranges))) as ex:
            chunks = list(ex.map(lambda r: (r, _fetch_range(url, r[0], r[1])), ranges))
        with open(dest, "wb") as f:
            f.truncate(total)
        with open(dest, "r+b") as f:
            for (s, e), data in chunks:
                if len(data) != e - s + 1:
                    return False
                f.seek(s)
                f.write(data)
        return True
    except Exception:  # noqa: BLE001
        return False


