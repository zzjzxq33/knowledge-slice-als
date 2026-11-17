"""转写服务商抽象接口。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float  # 秒
    end: float    # 秒
    text: str
    speaker: int | None = None

    def to_dict(self) -> dict:
        d = {"start": round(self.start, 2), "end": round(self.end, 2), "text": self.text}
        if self.speaker is not None:
            d["speaker"] = self.speaker
        return d


class TranscriptionError(Exception):
    """转写失败（信息可直接展示给用户）。"""


class ASRProvider(ABC):
    id = "base"
    label = ""

    def __init__(self, config):
        self.config = config

    @abstractmethod
    def transcribe(self, wav_path: Path, duration: float, options: dict, progress) -> list[Segment]:
        """
        对音频做语音转写。
        wav_path: 16kHz 单声道 16bit WAV；
        progress: 回调 (fraction: 0~1, message: str)。
        """
        raise NotImplementedError
