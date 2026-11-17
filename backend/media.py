"""ffmpeg / ffprobe 封装：探测、抽音轨、静音检测、音频切分。"""
import json
import re
import shutil
import subprocess
import wave
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

WAV_RATE = 16000  # 所有音频统一转成 16kHz 单声道 16bit PCM


class MediaError(Exception):
    """媒体处理失败。"""


def probe(path: Path) -> dict:
    """返回 {duration, has_audio, video_codec, audio_codec, width, height}。"""
    cmd = [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise MediaError(f"ffprobe 读取失败: {proc.stderr.strip()[:300]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise MediaError(f"ffprobe 输出解析失败: {e}")
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration": duration,
        "has_audio": audio is not None,
        "video_codec": (video or {}).get("codec_name"),
        "audio_codec": (audio or {}).get("codec_name"),
        "width": (video or {}).get("width"),
        "height": (video or {}).get("height"),
    }


def extract_audio(video_path: Path, wav_path: Path, duration: float, progress_cb=None) -> None:
    """从视频提取音轨，转为 16kHz 单声道 16bit WAV。progress_cb(0~1 比例)。"""
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-progress", "pipe:1",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", str(WAV_RATE), "-c:a", "pcm_s16le",
        str(wav_path),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        # -progress 输出 key=value；out_time_* 单位为微秒
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                sec = int(line.split("=", 1)[1].strip()) / 1_000_000
                if duration > 0 and progress_cb:
                    progress_cb(min(1.0, sec / duration))
            except ValueError:
                pass
    code = proc.wait()
    if code != 0:
        raise MediaError(f"ffmpeg 提取音轨失败（退出码 {code}）")


def detect_silences(wav_path: Path, noise_db: float = -35, min_dur: float = 0.3) -> list[tuple[float, float]]:
    """用 ffmpeg silencedetect 找出静音区间，返回 [(start, end), ...] 秒。"""
    cmd = [
        FFMPEG, "-hide_banner", "-nostdin", "-i", str(wav_path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return []
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", proc.stderr)]
    silences = []
    for s, e in zip(starts, ends):
        s = max(0.0, s)
        if e > s + 0.05:
            silences.append((s, e))
    return silences


def plan_chunks(duration: float, silences: list[tuple[float, float]],
                max_len: float) -> list[tuple[float, float]]:
    """把 [0, duration] 切成每段不超过 max_len 的区间，优先在静音中点处下刀。"""
    if duration <= 0:
        return [(0.0, 0.0)]
    cut_points = [(s + e) / 2 for s, e in silences if e - s >= 0.2]
    cut_points.sort()
    chunks = []
    pos = 0.0
    while pos < duration - 1e-6:
        remaining = duration - pos
        if remaining <= max_len:
            chunks.append((pos, duration))
            break
        lo = pos + max_len * 0.4
        hi = pos + max_len
        candidates = [p for p in cut_points if lo < p < hi and p - pos > 5]
        cut = max(candidates) if candidates else hi
        chunks.append((pos, cut))
        pos = cut
    # 合并过短的尾段（<0.5s 的尾部几乎没有内容）
    if len(chunks) > 1 and chunks[-1][1] - chunks[-1][0] < 0.5:
        chunks[-2] = (chunks[-2][0], chunks[-1][1])
        chunks.pop()
    return chunks


def read_pcm_frames(wav_path: Path, start: float, end: float) -> bytes:
    """读取 WAV 中 [start, end) 秒的原始 PCM 帧（要求 16bit 单声道）。"""
    with wave.open(str(wav_path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise MediaError("音频不是 16bit 单声道 WAV，无法切分")
        rate = w.getframerate()
        w.setpos(int(start * rate))
        n = int((end - start) * rate)
        return w.readframes(n)


def wav_slice_to_mp3(wav_path: Path, start: float, end: float, out_mp3: Path) -> None:
    """切出 WAV 的 [start, end) 段并转成 16kHz 单声道 32kbps mp3。"""
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(wav_path),
        "-ac", "1", "-ar", str(WAV_RATE), "-codec:a", "libmp3lame", "-b:a", "32k",
        str(out_mp3),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise MediaError(f"音频切片转 mp3 失败: {proc.stderr.strip()[:300]}")
