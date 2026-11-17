"""模拟转写：开发调试用，不调用真实 API。"""
import time
from pathlib import Path

from .base import ASRProvider, Segment, TranscriptionError

SAMPLE_SENTENCES = [
    "大家好，欢迎观看本期视频。",
    "今天我们来讲一个非常有意思的话题。",
    "首先介绍一下相关的背景知识。",
    "接下来我们通过几个例子来理解它。",
    "需要注意的是，这里有一个容易混淆的概念。",
    "我们可以用一张图来直观地展示这个过程。",
    "总结一下，今天的内容主要包括三个要点。",
    "最后，别忘了点赞和关注，我们下期再见。",
]


class MockProvider(ASRProvider):
    id = "mock"
    label = "模拟转写（开发调试）"

    def transcribe(self, wav_path: Path, duration: float, options: dict, progress) -> list[Segment]:
        if options.get("fail"):
            raise TranscriptionError("模拟失败（options.fail=true）")
        segments = []
        step = 6.0
        i = 0
        t = 0.5
        while t < max(duration - 0.5, 0.5):
            text = SAMPLE_SENTENCES[i % len(SAMPLE_SENTENCES)]
            end = min(t + 5.0, duration)
            segments.append(Segment(t, end, text))
            if progress:
                progress(min(1.0, t / duration), f"模拟转写中 {i + 1} 段")
            time.sleep(0.2)
            i += 1
            t += step
        return segments
