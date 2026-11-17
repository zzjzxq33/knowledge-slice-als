"""API 全流程测试（使用模拟转写，无需真实密钥）。"""
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from config import Config  # noqa: E402


def make_test_video(path: Path, seconds: int = 3, with_audio: bool = True) -> None:
    """生成带正弦音轨的测试视频。"""
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=15"]
    if with_audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                 "-c:a", "aac", "-shortest"]
    else:
        args += ["-an"]
    args += ["-c:v", "mpeg4", "-q:v", "5", str(path)]
    subprocess.run(args, check=True, capture_output=True)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        config = Config(base_dir=self.root, project_dir=self.root)
        config.storage_dir = self.root / "storage"
        config.database_path = self.root / "storage" / "jobs.db"
        config.enable_mock_provider = True
        config.worker_count = 2
        # 测试不依赖本地 .env 中的真实密钥
        config.xfyun_app_id = config.xfyun_api_key = config.xfyun_api_secret = ""
        config.tencent_secret_id = config.tencent_secret_key = ""
        self.app = create_app(config)
        self.client = self.app.test_client()

    def tearDown(self):
        manager = self.app.extensions["manager"]
        manager.shutdown()
        self.tmp.cleanup()

    def _upload(self, video: Path, provider: str = "mock") -> dict:
        with open(video, "rb") as f:
            resp = self.client.post(
                "/api/transcriptions",
                data={"file": (f, video.name), "provider": provider},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 202, resp.get_json())
        return resp.get_json()

    def _wait_complete(self, job_id: str, timeout: float = 60.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.client.get(f"/api/transcriptions/{job_id}").get_json()
            if job["status"] in ("completed", "failed"):
                return job
            time.sleep(0.2)
        self.fail("任务超时未完成")

    def test_full_flow(self):
        video = self.root / "test.mp4"
        make_test_video(video, seconds=3)
        job = self._upload(video)
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["original_name"], "test.mp4")

        done = self._wait_complete(job["id"])
        self.assertEqual(done["status"], "completed", done)
        self.assertGreater(done["duration"] or 0, 0)

        # 结果：带时间轴的文字稿
        result = self.client.get(f"/api/transcriptions/{job['id']}/result")
        self.assertEqual(result.status_code, 200)
        segments = result.get_json()["segments"]
        self.assertGreaterEqual(len(segments), 1)
        self.assertLessEqual(segments[0]["start"], segments[-1]["end"])
        self.assertTrue(segments[0]["text"])

        # 导出三种格式
        for fmt in ("srt", "vtt", "txt"):
            resp = self.client.get(f"/api/transcriptions/{job['id']}/export?format={fmt}")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("attachment", resp.headers["Content-Disposition"])

        # 视频回放，支持 Range
        resp = self.client.get(f"/api/transcriptions/{job['id']}/video")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Accept-Ranges"), "bytes")
        partial = self.client.get(
            f"/api/transcriptions/{job['id']}/video", headers={"Range": "bytes=0-99"}
        )
        self.assertEqual(partial.status_code, 206)

        # 已完成任务不允许重试
        self.assertEqual(
            self.client.post(f"/api/transcriptions/{job['id']}/retry").status_code, 409
        )

        # 列表与删除
        jobs = self.client.get("/api/transcriptions").get_json()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(self.client.delete(f"/api/transcriptions/{job['id']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/transcriptions/{job['id']}").status_code, 404)

    def test_export_with_chinese_filename(self):
        video = self.root / "线性代数.mp4"
        make_test_video(video, seconds=2)
        job = self._upload(video)
        self._wait_complete(job["id"])
        resp = self.client.get(f"/api/transcriptions/{job['id']}/export?format=srt")
        self.assertEqual(resp.status_code, 200)
        disposition = resp.headers["Content-Disposition"]
        self.assertIn("filename*=UTF-8''", disposition)
        self.assertIn("%E7%BA%BF%E6%80%A7", disposition)  # “线性”
        self.assertIn("-->", resp.get_data(as_text=True))

    def test_retry_failed_job(self):
        video = self.root / "retry.mp4"
        make_test_video(video, seconds=2)
        with open(video, "rb") as f:
            resp = self.client.post(
                "/api/transcriptions",
                data={"file": (f, "retry.mp4"), "provider": "mock",
                      "options": '{"fail": true}'},
                content_type="multipart/form-data",
            )
        job = resp.get_json()
        self.assertEqual(self._wait_complete(job["id"])["status"], "failed")

        resp = self.client.post(f"/api/transcriptions/{job['id']}/retry")
        self.assertEqual(resp.status_code, 202, resp.get_json())
        self.assertEqual(resp.get_json()["status"], "pending")
        self.assertIsNone(resp.get_json()["error"])

        # 复用原视频重跑，options 保留，因此仍会失败——验证任务确实被重新执行
        self.assertEqual(self._wait_complete(job["id"])["status"], "failed")
        # 不存在的任务
        self.assertEqual(
            self.client.post("/api/transcriptions/nope/retry").status_code, 404
        )

    def test_upload_validations(self):
        # 缺文件
        resp = self.client.post("/api/transcriptions", data={"provider": "mock"})
        self.assertEqual(resp.status_code, 400)
        # 未知服务商
        video = self.root / "t.mp4"
        make_test_video(video, seconds=1)
        with open(video, "rb") as f:
            resp = self.client.post(
                "/api/transcriptions",
                data={"file": (f, "t.mp4"), "provider": "xfyun"},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 400)
        # 无音轨视频
        silent = self.root / "silent.mp4"
        make_test_video(silent, seconds=1, with_audio=False)
        with open(silent, "rb") as f:
            resp = self.client.post(
                "/api/transcriptions",
                data={"file": (f, "silent.mp4"), "provider": "mock"},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 400)

    def test_config_endpoint(self):
        data = self.client.get("/api/config").get_json()
        self.assertEqual(data["max_upload_mb"], 2048)
        by_id = {p["id"]: p for p in data["providers"]}
        self.assertTrue(by_id["mock"]["configured"])
        self.assertFalse(by_id["xfyun"]["configured"])
        self.assertFalse(by_id["tencent"]["configured"])

    def test_failed_job(self):
        video = self.root / "fail.mp4"
        make_test_video(video, seconds=2)
        with open(video, "rb") as f:
            resp = self.client.post(
                "/api/transcriptions",
                data={"file": (f, "fail.mp4"), "provider": "mock",
                      "options": '{"fail": true}'},
                content_type="multipart/form-data",
            )
        job = resp.get_json()
        done = self._wait_complete(job["id"])
        self.assertEqual(done["status"], "failed")
        self.assertIn("模拟失败", done["error"])
        self.assertEqual(
            self.client.get(f"/api/transcriptions/{job['id']}/result").status_code, 409
        )


if __name__ == "__main__":
    unittest.main()
