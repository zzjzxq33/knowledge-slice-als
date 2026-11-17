"""后台任务管理：抽取音轨 -> 语音转写 -> 生成带时间轴的文字稿。"""
import json
import logging
import shutil
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import media

log = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "extracting", "transcribing")


class JobManager:
    def __init__(self, config, store, providers):
        self.config = config
        self.store = store
        self.providers = providers
        self.executor = ThreadPoolExecutor(
            max_workers=config.worker_count, thread_name_prefix="asr-worker"
        )

    def submit(self, job_id: str) -> None:
        self.executor.submit(self._run, job_id)

    def recover(self) -> None:
        """服务重启后，把中断的任务重新排队。"""
        for job in self.store.list(limit=1000):
            if job["status"] in ACTIVE_STATUSES:
                self.store.update(job["id"], status="pending", message="排队中（服务重启后恢复）")
                self.submit(job["id"])

    # ---- 任务主流程 ----

    def _run(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if not job:
            return
        try:
            self._process(job)
        except Exception as e:  # noqa: BLE001 —— 任何异常都要落库呈现给用户
            log.exception("job %s failed", job_id)
            self.store.update(
                job_id, status="failed", message="处理失败",
                error=str(e) or e.__class__.__name__,
            )

    def _process(self, job: dict) -> None:
        job_id = job["id"]
        job_dir = self.config.job_dir(job_id)
        video_path = job_dir / job["video_filename"]
        audio_path = job_dir / job["audio_filename"]
        provider = self.providers.get(job["provider"])
        if provider is None:
            raise RuntimeError(f"转写服务商不可用: {job['provider']}")

        self.store.update(job_id, status="extracting", progress=1, message="读取视频信息")
        meta = media.probe(video_path)
        if not meta["has_audio"]:
            raise media.MediaError("视频中没有音轨")
        duration = meta["duration"]
        self.store.update(job_id, duration=round(duration, 2))

        def extract_cb(fraction):
            self.store.update(job_id, progress=1 + fraction * 19, message="提取音轨")

        media.extract_audio(video_path, audio_path, duration, extract_cb)

        self.store.update(job_id, status="transcribing", progress=20, message="分析音频静音段")
        options = json.loads(job["options"] or "{}")

        def asr_cb(fraction, message):
            self.store.update(job_id, progress=20 + fraction * 75, message=message)

        segments = provider.transcribe(audio_path, duration, options, asr_cb)

        result = {
            "provider": job["provider"],
            "duration": round(duration, 2),
            "segments": [
                {"id": i, **seg.to_dict()} for i, seg in enumerate(segments)
            ],
        }
        count = len(segments)
        self.store.update(
            job_id, status="completed", progress=100,
            message="转写完成" if count else "未识别到语音内容",
            result=json.dumps(result, ensure_ascii=False),
        )
        log.info("job %s completed: %d segments, %.1fs audio", job_id, count, duration)

    # ---- 清理 ----

    def delete_job(self, job_id: str) -> None:
        self.store.delete(job_id)
        shutil.rmtree(self.config.job_dir(job_id), ignore_errors=True)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)
