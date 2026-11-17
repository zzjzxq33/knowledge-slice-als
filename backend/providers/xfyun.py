"""讯飞语音听写（WebSocket 流式版，iat-api.xfyun.cn/v2/iat）。

每个 WebSocket 会话最多处理约 60s 音频，长音频按静音点切成
不超过 max_chunk_seconds 的小段，逐段转写后拼接时间轴。

鉴权：HMAC-SHA256 对 "host/date/request-line" 签名，见
https://www.xfyun.cn/doc/asr/voicedictation/API.html
"""
import base64
import hashlib
import hmac
import json
import time
from email.utils import formatdate
from pathlib import Path
from urllib.parse import urlencode

import websocket

from media import detect_silences, plan_chunks, read_pcm_frames
from utils import proportional_segments
from .base import ASRProvider, Segment, TranscriptionError

IAT_HOST = "iat-api.xfyun.cn"
IAT_PATH = "/v2/iat"
FRAME_BYTES = 1280  # 40ms 音频 = 16000Hz * 2字节 * 0.04s
MAX_RESULT_FRAMES = 20000  # 防死循环


class XfyunIatProvider(ASRProvider):
    id = "xfyun"
    label = "讯飞语音听写"

    def __init__(self, config):
        super().__init__(config)
        self.app_id = config.xfyun_app_id
        self.api_key = config.xfyun_api_key
        self.api_secret = config.xfyun_api_secret
        self.max_chunk_seconds = config.xfyun_chunk_seconds
        self.frame_sleep = config.xfyun_frame_sleep

    def _build_url(self) -> str:
        date = formatdate(usegmt=True)
        signature_origin = f"host: {IAT_HOST}\ndate: {date}\nGET {IAT_PATH} HTTP/1.1"
        signature_sha = base64.b64encode(
            hmac.new(self.api_secret.encode(), signature_origin.encode(), hashlib.sha256).digest()
        ).decode()
        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature_sha}"'
        )
        authorization = base64.b64encode(authorization_origin.encode()).decode()
        query = urlencode({"authorization": authorization, "date": date, "host": IAT_HOST})
        return f"wss://{IAT_HOST}{IAT_PATH}?{query}"

    def _frame(self, status: int, audio: bytes = b"") -> str:
        return json.dumps({
            "common": {"app_id": self.app_id},
            "business": {
                "language": "zh_cn",
                "domain": "iat",
                "accent": "mandarin",
                "dwa": "wpgs",      # 动态修正：结果先出后改
                "ptt": 1,           # 加标点符号
                "vad_eos": 10000,   # 端点检测，长静音结束当前语音
            },
            "data": {
                "status": status,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": base64.b64encode(audio).decode(),
            },
        })

    def transcribe(self, wav_path: Path, duration: float, options: dict, progress) -> list[Segment]:
        silences = detect_silences(wav_path)
        chunks = plan_chunks(duration, silences, self.max_chunk_seconds)
        segments: list[Segment] = []
        total = len(chunks)
        for idx, (start, end) in enumerate(chunks):
            pcm = read_pcm_frames(wav_path, start, end)
            text = self._transcribe_pcm(pcm)
            if text:
                segments.extend(
                    Segment(s, e, t) for s, e, t in proportional_segments(text, start, end)
                )
            if progress:
                progress((idx + 1) / total, f"讯飞转写中 {idx + 1}/{total} 段")
        return segments

    def _transcribe_pcm(self, pcm: bytes) -> str:
        if not pcm:
            return ""
        ws = websocket.create_connection(self._build_url(), timeout=20)
        try:
            # 第一帧带前 40ms 音频
            ws.send(self._frame(0, pcm[:FRAME_BYTES]))
            rest = pcm[FRAME_BYTES:]
            for i in range(0, len(rest), FRAME_BYTES):
                if self.frame_sleep:
                    time.sleep(self.frame_sleep)
                ws.send(self._frame(1, rest[i:i + FRAME_BYTES]))
            if self.frame_sleep:
                time.sleep(self.frame_sleep)
            ws.send(self._frame(2))  # 最后一帧：status=2，空音频

            parts: dict[int, str] = {}
            for _ in range(MAX_RESULT_FRAMES):
                msg = json.loads(ws.recv())
                code = msg.get("code", 0)
                if code != 0:
                    raise TranscriptionError(f"讯飞返回错误 {code}: {msg.get('message')}")
                data = msg.get("data") or {}
                result = data.get("result")
                if result:
                    self._merge_result(parts, result)
                if data.get("status") == 2:
                    break
            return "".join(parts[sn] for sn in sorted(parts))
        except websocket.WebSocketException as e:
            raise TranscriptionError(f"讯飞接口连接失败: {e}")
        finally:
            ws.close()

    @staticmethod
    def _merge_result(parts: dict[int, str], result: dict) -> None:
        """按动态修正协议合并：pgs=rpl 时用新结果替换 rg 范围内的旧结果。"""
        sn = result.get("sn")
        text = ""
        for ws_item in result.get("ws") or []:
            cw = ws_item.get("cw") if isinstance(ws_item, dict) else None
            if cw:
                text += cw[0].get("w", "")
        if result.get("pgs") == "rpl":
            rg = result.get("rg") or [sn, sn]
            for k in range(rg[0], rg[1] + 1):
                parts.pop(k, None)
        parts[sn] = text
