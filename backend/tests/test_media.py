"""media / utils 纯逻辑测试。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from media import detect_silences, plan_chunks, read_pcm_frames, WAV_RATE  # noqa: E402
from utils import proportional_segments, segments_to_srt, split_sentences, srt_timestamp  # noqa: E402


def make_silence_wav(path: Path) -> None:
    """2s 正弦 + 1s 静音 + 2s 正弦 -> 16k 单声道 wav。"""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1",
         "-ar", str(WAV_RATE), "-ac", "1", str(path)],
        check=True, capture_output=True,
    )


class SplitSentencesTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(split_sentences("第一句。第二句！"), ["第一句。", "第二句！"])

    def test_no_punctuation_hard_wrap(self):
        result = split_sentences("字" * 100, max_len=60)
        self.assertGreaterEqual(len(result), 2)
        self.assertTrue(all(len(s) <= 60 for s in result))

    def test_proportional(self):
        segs = proportional_segments("一二。三四五六。", 10.0, 20.0)
        self.assertEqual(len(segs), 2)
        self.assertAlmostEqual(segs[0][0], 10.0, places=2)
        self.assertAlmostEqual(segs[-1][1], 20.0, places=2)

    def test_srt(self):
        self.assertEqual(srt_timestamp(3661.234), "01:01:01,234")
        text = segments_to_srt([{"start": 0.0, "end": 2.5, "text": "你好。"}])
        self.assertIn("00:00:00,000 --> 00:00:02,500", text)
        self.assertIn("你好。", text)


class ChunkTest(unittest.TestCase):
    def test_silence_split(self):
        # 70s 音频、20s 上限、静音中点在 10.5 / 30.5 / 50.5
        silences = [(10, 11), (30, 31), (50, 51)]
        chunks = plan_chunks(70, silences, 20)
        for s, e in chunks:
            self.assertLessEqual(e - s, 20 + 1e-6)
        self.assertEqual(chunks[0][0], 0.0)
        self.assertAlmostEqual(chunks[-1][1], 70.0, places=3)
        self.assertAlmostEqual(chunks[0][1], 10.5, places=3)

    def test_no_silence_fixed_cut(self):
        chunks = plan_chunks(45, [], 20)
        self.assertEqual(chunks, [(0.0, 20.0), (20.0, 40.0), (40.0, 45.0)])

    def test_tiny_tail_merged(self):
        chunks = plan_chunks(21.2, [], 20)
        self.assertEqual(len(chunks), 2)
        self.assertAlmostEqual(chunks[-1][1], 21.2, places=3)


class SilenceDetectTest(unittest.TestCase):
    def test_detect_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "s.wav"
            make_silence_wav(wav)
            silences = detect_silences(wav)
            self.assertTrue(
                any(abs(s - 2.0) < 0.4 for s, _ in silences),
                f"未检测到 2s 处静音: {silences}",
            )
            pcm = read_pcm_frames(wav, 1.0, 2.0)
            self.assertEqual(len(pcm), WAV_RATE * 2)  # 16bit 单声道 = 每帧 2 字节


if __name__ == "__main__":
    unittest.main()
