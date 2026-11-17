"""应用配置：从环境变量 / .env 文件读取。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

# 优先加载 backend/.env，其次项目根目录 .env
load_dotenv(BASE_DIR / ".env")
load_dotenv(PROJECT_DIR / ".env")


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


class Config:
    def __init__(self, base_dir: Path = None, project_dir: Path = None):
        self.base_dir = base_dir or BASE_DIR
        self.project_dir = project_dir or PROJECT_DIR

        # 服务
        self.host = os.getenv("HOST", "127.0.0.1")
        self.port = _env_int("PORT", 5000)
        self.debug = _env_bool("FLASK_DEBUG", "0")
        self.cors_origins = os.getenv("CORS_ORIGINS", "*")

        # 存储
        self.storage_dir = Path(os.getenv("STORAGE_DIR", str(self.base_dir / "storage")))
        self.database_path = Path(os.getenv("DATABASE_PATH", str(self.storage_dir / "jobs.db")))
        self.max_upload_mb = _env_int("MAX_UPLOAD_MB", 2048)
        self.worker_count = max(1, _env_int("WORKER_COUNT", 2))

        # 讯飞语音听写（WebSocket 流式版）
        self.xfyun_app_id = os.getenv("XFYUN_APP_ID", "")
        self.xfyun_api_key = os.getenv("XFYUN_API_KEY", "")
        self.xfyun_api_secret = os.getenv("XFYUN_API_SECRET", "")
        # 每个 WebSocket 会话最多 60s 音频，这里留出余量
        self.xfyun_chunk_seconds = min(58.0, _env_float("XFYUN_CHUNK_SECONDS", 55.0))
        # 每发一帧(40ms)音频的间隔；0.01≈4倍速发送，调大更稳妥，0 为全速
        self.xfyun_frame_sleep = _env_float("XFYUN_FRAME_SLEEP", 0.01)

        # 腾讯云录音文件识别
        self.tencent_secret_id = os.getenv("TENCENT_SECRET_ID", "")
        self.tencent_secret_key = os.getenv("TENCENT_SECRET_KEY", "")
        # 分片上限（秒），每片转成 mp3 后约 1.2MB，远低于接口 5MB 限制
        self.tencent_chunk_seconds = _env_float("TENCENT_CHUNK_SECONDS", 280.0)
        self.tencent_default_engine = os.getenv("TENCENT_ENGINE", "16k_zh")
        # 提交任务后轮询间隔（秒）
        self.tencent_poll_interval = _env_float("TENCENT_POLL_INTERVAL", 1.5)

        # 开发用：模拟转写，无需真实密钥
        self.enable_mock_provider = _env_bool("ENABLE_MOCK_PROVIDER", "0")

    # ---- 派生属性 ----

    @property
    def xfyun_configured(self) -> bool:
        return all([self.xfyun_app_id, self.xfyun_api_key, self.xfyun_api_secret])

    @property
    def tencent_configured(self) -> bool:
        return all([self.tencent_secret_id, self.tencent_secret_key])

    def job_dir(self, job_id: str) -> Path:
        return self.storage_dir / "jobs" / job_id
