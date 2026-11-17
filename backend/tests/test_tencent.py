"""腾讯云 provider 纯逻辑测试（不发起网络请求）。"""
import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config  # noqa: E402
from providers.base import TranscriptionError  # noqa: E402
from providers.tencent import TencentProvider  # noqa: E402


class TencentPayloadTest(unittest.TestCase):
    def setUp(self):
        config = Config()
        config.tencent_secret_id = "sid"
        config.tencent_secret_key = "skey"
        self.provider = TencentProvider(config)

    def test_payload_uses_only_supported_fields(self):
        payload = self.provider._build_create_payload(
            b"abc", {"engine": "16k_zh", "speaker_diarization": True}
        )
        # 接口对未知参数返回 UnknownParameter（ConvertNumFormat 曾触发此错误）
        self.assertEqual(
            set(payload),
            {
                "EngineModelType", "ChannelNum", "ResTextFormat", "SourceType",
                "Data", "DataLen", "FilterDirty", "FilterModal",
                "SpeakerDiarization", "SpeakerNumber",
            },
        )
        self.assertNotIn("ConvertNumFormat", payload)
        self.assertEqual(payload["Data"], base64.b64encode(b"abc").decode())
        self.assertEqual(payload["DataLen"], 3)
        self.assertEqual(payload["SpeakerDiarization"], 1)
        self.assertEqual(payload["SourceType"], 1)  # 1 = base64 音频数据
        self.assertNotIn("Url", payload)

    def test_invalid_engine_rejected(self):
        with self.assertRaises(TranscriptionError):
            self.provider._build_create_payload(b"", {"engine": "not_an_engine"})

    def test_default_engine(self):
        payload = self.provider._build_create_payload(b"", {})
        self.assertEqual(payload["EngineModelType"], self.provider.default_engine)


class TencentResultParseTest(unittest.TestCase):
    def test_result_detail_preferred(self):
        # 真实响应结构：ResultDetail 为句级列表（StartMs/EndMs 毫秒）
        data = {
            "AudioDuration": 60,
            "Result": "[0:0.000,0:1.500]  你好。\n",
            "ResultDetail": [
                {"FinalSentence": "你好。", "StartMs": 1000, "EndMs": 2340, "SpeakerId": 2}
            ],
        }
        segments = TencentProvider._parse_task_result(
            data, 5.0, 60, include_speaker=True
        )
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].start, 6.0)
        self.assertEqual(segments[0].end, 7.34)
        self.assertEqual(segments[0].speaker, 2)

    def test_speaker_omitted_when_diarization_disabled(self):
        data = {"ResultDetail": [
            {"FinalSentence": "你好。", "StartMs": 0, "EndMs": 1000, "SpeakerId": 0}
        ]}
        segments = TencentProvider._parse_task_result(data, 0, 10, include_speaker=False)
        self.assertIsNone(segments[0].speaker)

    def test_fallback_json_result_seconds(self):
        data = {
            "Result": '{"result":[{"sentence":"你好。","start_time":1,"end_time":2.5}],'
                      '"audio_duration":14}'
        }
        segments = TencentProvider._parse_task_result(data, 0, 14)
        self.assertEqual(segments[0].start, 1.0)
        self.assertEqual(segments[0].end, 2.5)

    def test_fallback_plain_text(self):
        data = {"Result": "[0:0.000,0:3.500]  第一句。\n[0:4.000,0:8.500]  第二句。"}
        segments = TencentProvider._parse_task_result(data, 10.0, 20)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].start, 10.0)
        self.assertEqual(segments[0].end, 13.5)
        self.assertEqual(segments[1].start, 14.0)
        self.assertEqual(segments[1].text, "第二句。")

    def test_empty_result(self):
        self.assertEqual(TencentProvider._parse_task_result({}, 0, 10), [])
        self.assertEqual(TencentProvider._parse_task_result({"Result": ""}, 0, 10), [])
        self.assertEqual(
            TencentProvider._parse_task_result({"ResultDetail": []}, 0, 10), []
        )


if __name__ == "__main__":
    unittest.main()
