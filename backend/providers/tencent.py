"""腾讯云录音文件识别（CreateRecTask / DescribeTaskStatus）。

音频以 base64（SourceType=0）直接提交，不依赖公网 URL；
长音频按静音点切成不超过 max_chunk_seconds 的片，每片转 mp3（约 1.2MB，
低于接口 5MB 限制），逐片提交并轮询结果。

鉴权：TC3-HMAC-SHA256，见
https://cloud.tencent.com/document/product/1093/37823
"""
import base64
import hashlib
import hmac
import json
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from media import detect_silences, plan_chunks, wav_slice_to_mp3
from .base import ASRProvider, Segment, TranscriptionError

TENCENT_ASR_HOST = "asr.tencentcloudapi.com"
TENCENT_ASR_SERVICE = "asr"
TENCENT_ASR_VERSION = "2019-06-14"

ENGINES = {
    "16k_zh": "16k 中文普通话·通用",
    "16k_zh_video": "16k 中文普通话·音视频领域",
    "16k_zh_large": "16k 中文普通话·大模型版",
    "8k_zh": "8k 中文普通话·电话",
}

# Result 纯文本格式：每行 "[0:0.000,0:40.080]  识别文本"
_TEXT_LINE_RE = re.compile(r"\[([0-9:.]+)\s*,\s*([0-9:.]+)\]\s*(.+)")


def _parse_clock(value: str) -> float:
    """"m:ss.mmm" / "h:mm:ss.mmm" -> 秒。"""
    try:
        parts = [float(p) for p in value.strip().split(":")]
    except ValueError:
        return 0.0
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0] if parts else 0.0


class TencentProvider(ASRProvider):
    id = "tencent"
    label = "腾讯云录音文件识别"

    def __init__(self, config):
        super().__init__(config)
        self.secret_id = config.tencent_secret_id
        self.secret_key = config.tencent_secret_key
        self.max_chunk_seconds = config.tencent_chunk_seconds
        self.default_engine = config.tencent_default_engine
        self.poll_interval = config.tencent_poll_interval
        self.session = requests.Session()

    # ---- TC3 签名 ----

    def _request(self, action: str, payload: dict) -> dict:
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        ct = "application/json; charset=utf-8"
        body = json.dumps(payload, ensure_ascii=False)
        signed_headers = "content-type;host;x-tc-action"
        canonical_headers = f"content-type:{ct}\nhost:{TENCENT_ASR_HOST}\nx-tc-action:{action.lower()}\n"
        hashed_payload = hashlib.sha256(body.encode()).hexdigest()
        canonical_request = "\n".join([
            "POST", "/", "", canonical_headers, signed_headers, hashed_payload,
        ])
        credential_scope = f"{date}/{TENCENT_ASR_SERVICE}/tc3_request"
        hashed_canonical = hashlib.sha256(canonical_request.encode()).hexdigest()
        string_to_sign = "\n".join([
            "TC3-HMAC-SHA256", str(timestamp), credential_scope, hashed_canonical,
        ])

        def sign(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        secret_date = sign(("TC3" + self.secret_key).encode(), date)
        secret_service = sign(secret_date, TENCENT_ASR_SERVICE)
        secret_signing = sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
        authorization = (
            f"TC3-HMAC-SHA256 Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            "Authorization": authorization,
            "Content-Type": ct,
            "Host": TENCENT_ASR_HOST,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": TENCENT_ASR_VERSION,
        }
        try:
            resp = self.session.post(
                f"https://{TENCENT_ASR_HOST}/", headers=headers,
                data=body.encode(), timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            raise TranscriptionError(f"腾讯云请求失败: {e}")
        response = data.get("Response") or {}
        if response.get("Error"):
            err = response["Error"]
            raise TranscriptionError(f"腾讯云接口错误: {err.get('Code')} {err.get('Message')}")
        return response

    # ---- 转写 ----

    def transcribe(self, wav_path: Path, duration: float, options: dict, progress) -> list[Segment]:
        silences = detect_silences(wav_path)
        chunks = plan_chunks(duration, silences, self.max_chunk_seconds)
        segments: list[Segment] = []
        total = len(chunks)
        tmp_dir = Path(tempfile.mkdtemp(prefix="tencent-chunks-", dir=str(wav_path.parent)))
        try:
            for idx, (start, end) in enumerate(chunks):
                mp3 = tmp_dir / f"{idx:04d}.mp3"
                wav_slice_to_mp3(wav_path, start, end, mp3)
                task_id = self._create_task(mp3.read_bytes(), options)
                task_data = self._poll(task_id, end - start)
                segments.extend(self._parse_task_result(
                    task_data, start, end,
                    include_speaker=bool(options.get("speaker_diarization")),
                ))
                if progress:
                    progress((idx + 1) / total, f"腾讯云转写中 {idx + 1}/{total} 段")
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return segments

    def _build_create_payload(self, audio: bytes, options: dict) -> dict:
        """注意：接口对未知参数会直接报 UnknownParameter（如 ConvertNumFormat），
        这里只发送录音文件识别明确支持的字段。"""
        engine = options.get("engine") or self.default_engine
        if engine not in ENGINES:
            raise TranscriptionError(f"不支持的引擎: {engine}")
        return {
            "EngineModelType": engine,
            "ChannelNum": 1,
            "ResTextFormat": 2,  # 详细结果：句子 + 词级时间戳 + 标点
            "SourceType": 1,     # 1 = base64 音频数据（0 = 音频 URL）
            "Data": base64.b64encode(audio).decode(),
            "DataLen": len(audio),
            "FilterDirty": 1 if options.get("filter_dirty") else 0,
            "FilterModal": 1 if options.get("filter_modal") else 0,
            "SpeakerDiarization": 1 if options.get("speaker_diarization") else 0,
            "SpeakerNumber": 0,
        }

    def _create_task(self, audio: bytes, options: dict) -> int:
        payload = self._build_create_payload(audio, options)
        response = self._request("CreateRecTask", payload)
        task_id = (response.get("Data") or {}).get("TaskId")
        if not task_id:
            raise TranscriptionError("腾讯云未返回 TaskId")
        return task_id

    def _poll(self, task_id: int, chunk_duration: float) -> dict:
        deadline = time.time() + max(90, chunk_duration * 2)
        while True:
            response = self._request("DescribeTaskStatus", {"TaskId": task_id})
            data = response.get("Data") or {}
            status = data.get("Status")
            if status == 2:  # 成功，返回完整 Data（含 Result / ResultDetail）
                return data
            if status == 3:  # 失败
                raise TranscriptionError(f"腾讯云转写失败: {data.get('ErrorMsg') or '未知错误'}")
            if time.time() > deadline:
                raise TranscriptionError(f"腾讯云转写超时（TaskId {task_id}）")
            time.sleep(self.poll_interval)

    @staticmethod
    def _parse_task_result(data: dict, offset: float, chunk_duration: float,
                           include_speaker: bool = False) -> list[Segment]:
        """优先使用 ResultDetail（句级毫秒时间戳），兼容 Result 的 JSON / 纯文本格式。"""
        if not data:
            return []
        details = data.get("ResultDetail")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                details = None
        if isinstance(details, list) and details:
            return TencentProvider._parse_detail(details, offset, include_speaker)

        raw = data.get("Result")
        if isinstance(raw, (dict, list)):
            return TencentProvider._parse_json_result(raw, offset, chunk_duration, include_speaker)
        if isinstance(raw, str) and raw.strip():
            text = raw.strip()
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return TencentProvider._parse_text_result(text, offset)
            return TencentProvider._parse_json_result(parsed, offset, chunk_duration, include_speaker)
        return []

    @staticmethod
    def _parse_detail(details: list[dict], offset: float, include_speaker: bool) -> list[Segment]:
        segments = []
        for item in details:
            if not isinstance(item, dict):
                continue
            text = (item.get("FinalSentence") or "").strip()
            if not text:
                continue
            start = (item.get("StartMs") or 0) / 1000 + offset
            end = (item.get("EndMs") or 0) / 1000 + offset
            if end <= start:
                end = start + 0.5
            seg = Segment(start, end, text)
            if include_speaker and item.get("SpeakerId") not in (None, ""):
                seg.speaker = item.get("SpeakerId")
            segments.append(seg)
        return segments

    @staticmethod
    def _parse_json_result(data, offset: float, chunk_duration: float,
                           include_speaker: bool) -> list[Segment]:
        sentences = data.get("result") if isinstance(data, dict) else data
        if not isinstance(sentences, list):
            return []
        factor = TencentProvider._time_factor(data, sentences, chunk_duration)
        segments = []
        for item in sentences:
            if not isinstance(item, dict):
                continue
            text = (item.get("sentence") or "").strip()
            if not text:
                continue
            start = (item.get("start_time") or 0) * factor + offset
            end = (item.get("end_time") or 0) * factor + offset
            if end <= start:
                end = start + 0.5
            seg = Segment(start, end, text)
            if include_speaker and item.get("speaker_id") not in (None, ""):
                seg.speaker = item.get("speaker_id")
            segments.append(seg)
        return segments

    @staticmethod
    def _parse_text_result(text: str, offset: float) -> list[Segment]:
        """解析 "[0:0.000,0:40.080]  文本" 格式的旧版纯文本结果。"""
        segments = []
        for line in text.splitlines():
            m = _TEXT_LINE_RE.match(line.strip())
            if not m:
                continue
            start = _parse_clock(m.group(1)) + offset
            end = _parse_clock(m.group(2)) + offset
            sentence = m.group(3).strip()
            if not sentence:
                continue
            if end <= start:
                end = start + 0.5
            segments.append(Segment(start, end, sentence))
        return segments

    @staticmethod
    def _time_factor(data, sentences: list[dict], chunk_duration: float) -> float:
        """仅用于备用 JSON 格式：时间单位可能是毫秒或秒，用 audio_duration / 最大 end_time 推断。"""
        if isinstance(data, dict):
            audio_duration = data.get("audio_duration")
            if audio_duration:
                if audio_duration > chunk_duration * 10:
                    return 1 / 1000
                if audio_duration <= chunk_duration * 1.5:
                    return 1.0
        max_end = max(
            (s.get("end_time") or 0 for s in sentences if isinstance(s, dict)), default=0
        )
        if max_end > chunk_duration * 10:
            return 1 / 1000
        if max_end <= chunk_duration * 1.5:
            return 1.0
        return 1 / 1000
