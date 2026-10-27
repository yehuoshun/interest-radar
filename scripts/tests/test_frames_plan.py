"""_SparsePlan：sample→chunk 映射与 offset 计算（stts/stsc/stco/stsz 交叉验证）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import frames as F

# 手造小表：stsc = [(1,3,1),(2,2,1),(4,3,1)] → 6 chunks, 16 samples
# chunk0=3 samples, chunk1-2=2, chunk3-5=3
STTS = [1, 544, 2, 528, 1, 544]  # 简单
STSS = [1, 9, 16]
STSC = [1, 3, 1, 2, 2, 1, 4, 3, 1]
# 16 samples：size 全部 100，chunk offsets 从 1000 起每 chunk 递增
STSZ = [100] * 16
STCO = [1000, 1300, 1500, 1700, 2000, 2300]
MOOV_END = 500


def make_plan():
    return F._SparsePlan(zone=b"", moov_off=0, moov_size=0, stbl_off=0,
                         timescale=16000, stts=STTS, stss=STSS, stsc=STSC,
                         stsz=STSZ, stco=STCO, moov_end=MOOV_END)


class TestSampleChunk(unittest.TestCase):
    def test_boundaries(self):
        p = make_plan()
        # idx=0,2 → chunk0; idx=3 → chunk1; idx=5 → chunk2; idx=7 → chunk3; idx=15 → chunk5
        self.assertEqual(p._sample_chunk(0), (0, 0))
        self.assertEqual(p._sample_chunk(2), (0, 2))
        self.assertEqual(p._sample_chunk(3), (1, 0))
        self.assertEqual(p._sample_chunk(5), (2, 0))
        self.assertEqual(p._sample_chunk(7), (3, 0))
        self.assertEqual(p._sample_chunk(15), (5, 2))

    def test_offsets(self):
        p = make_plan()
        # chunk0 起点 1000；sample0 → 1000, sample2 → 1200（chunk0 内第 3 个）
        self.assertEqual(p._sample_offset(0), (1000, 100))
        self.assertEqual(p._sample_offset(2), (1200, 100))
        # sample3 → chunk1 起点 1300；sample5 → chunk2 起点 1500 + 100
        self.assertEqual(p._sample_offset(3), (1300, 100))
        self.assertEqual(p._sample_offset(5), (1500, 100))
        # sample7 → chunk3 起点 1700；sample15 → chunk5 起点 2300 + 200
        self.assertEqual(p._sample_offset(7), (1700, 100))
        self.assertEqual(p._sample_offset(15), (2500, 100))


class TestRanges(unittest.TestCase):
    def test_ranges_include_moov_and_pad(self):
        p = make_plan()
        ranges = p.ranges([1.0], pad=64)
        # moov 区 [0, 500) + 采样段
        self.assertEqual(ranges[0], (0, 500))
        self.assertTrue(all(s < e for s, e in ranges))

    def test_stts_sample_selection_respects_base(self):
        """stts 偏移必须加 entry 前的累计 sample 数（10-27 踩过的坑）。"""
        p = make_plan()
        # t = (544 + 528 + 100) / 16000 ≈ 0.073s → 落在第 3 个 entry
        # entry0: 1 sample, entry1: 2 samples → sample_base=3
        ranges = p.ranges([(544 + 528 + 100) / 16000], pad=0)
        seg = [r for r in ranges if r[0] > MOOV_END][0]
        # 目标 sample#4（idx=3）→ offset 1300；关键帧 stss ≤4 → 1 → 1000
        self.assertEqual(seg[0], 1000)
        self.assertGreaterEqual(seg[1], 1300)


if __name__ == "__main__":
    unittest.main()