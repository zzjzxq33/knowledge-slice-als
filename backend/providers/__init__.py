"""转写服务商注册与信息。"""
from .base import ASRProvider, Segment, TranscriptionError
from .mock import MockProvider
from .tencent import ENGINES, TencentProvider
from .xfyun import XfyunIatProvider

__all__ = ["ASRProvider", "Segment", "TranscriptionError",
           "XfyunIatProvider", "TencentProvider", "MockProvider",
           "build_providers", "provider_info"]


def build_providers(config) -> dict[str, ASRProvider]:
    """按配置返回可用的转写服务商。"""
    providers: dict[str, ASRProvider] = {}
    if config.xfyun_configured:
        providers["xfyun"] = XfyunIatProvider(config)
    if config.tencent_configured:
        providers["tencent"] = TencentProvider(config)
    if config.enable_mock_provider:
        providers["mock"] = MockProvider(config)
    return providers


def provider_info(config) -> list[dict]:
    """供前端 /api/config 展示：所有服务商 + 是否已配置密钥。"""
    return [
        {
            "id": "xfyun",
            "label": "讯飞开放平台 · 语音听写",
            "configured": config.xfyun_configured,
            "hint": "在 backend/.env 中配置 XFYUN_APP_ID / XFYUN_API_KEY / XFYUN_API_SECRET",
            "engines": [],
            "default_engine": None,
            "supports_speaker": False,
        },
        {
            "id": "tencent",
            "label": "腾讯云 · 录音文件识别",
            "configured": config.tencent_configured,
            "hint": "在 backend/.env 中配置 TENCENT_SECRET_ID / TENCENT_SECRET_KEY",
            "engines": [{"id": k, "label": v} for k, v in ENGINES.items()],
            "default_engine": config.tencent_default_engine,
            "supports_speaker": True,
        },
        {
            "id": "mock",
            "label": "模拟转写（开发调试）",
            "configured": config.enable_mock_provider,
            "hint": "设置 ENABLE_MOCK_PROVIDER=1 开启",
            "engines": [],
            "default_engine": None,
            "supports_speaker": False,
        },
    ]
