"""通用工具：文本切句、时间格式、字幕导出。"""
import re


def split_sentences(text: str, max_len: int = 60) -> list[str]:
    """按句末标点切句；无标点的超长片段按 max_len 硬切。"""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sentences: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？；!?;…\n" or len(buf) >= max_len:
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
    if buf.strip():
        sentences.append(buf.strip())
    return sentences


def proportional_segments(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    """把一段文本按字符数比例分摊到 [start, end] 时间区间，返回 (start, end, text)。"""
    sentences = split_sentences(text)
    if not sentences:
        return []
    total = sum(len(s) for s in sentences) or 1
    segments = []
    t = start
    for s in sentences:
        dur = (end - start) * len(s) / total
        segments.append((t, t + dur, s))
        t += dur
    return segments


def _hms_ms(seconds: float, sep: str) -> str:
    ms_total = int(round(max(0.0, seconds) * 1000))
    h = ms_total // 3600000
    m = (ms_total % 3600000) // 60000
    s = (ms_total % 60000) // 1000
    ms = ms_total % 1000
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def srt_timestamp(seconds: float) -> str:
    return _hms_ms(seconds, ",")


def vtt_timestamp(seconds: float) -> str:
    return _hms_ms(seconds, ".")


def txt_timestamp(seconds: float) -> str:
    total = int(max(0.0, seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def segments_to_srt(segments: list[dict]) -> str:
    lines = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{srt_timestamp(seg['start'])} --> {srt_timestamp(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def segments_to_vtt(segments: list[dict]) -> str:
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(f"{vtt_timestamp(seg['start'])} --> {vtt_timestamp(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def segments_to_txt(segments: list[dict]) -> str:
    return "\n".join(f"[{txt_timestamp(seg['start'])}] {seg['text']}" for seg in segments)
