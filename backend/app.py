"""Flask 入口：视频上传、任务查询、结果/字幕导出、视频回放。

运行：cd backend && python app.py
"""
import json
import logging
import mimetypes
import shutil
import uuid
from pathlib import Path
from urllib.parse import quote

from flask import Flask, abort, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import safe_join

import media
from config import Config
from db import JobStore
from jobs import JobManager
from providers import build_providers, provider_info
from utils import segments_to_srt, segments_to_txt, segments_to_vtt

ALLOWED_VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv",
    ".m4v", ".ts", ".mpg", ".mpeg", ".3gp", ".rmvb",
}
EXPORT_FORMATS = {"srt": segments_to_srt, "vtt": segments_to_vtt, "txt": segments_to_txt}


def _public(job: dict) -> dict:
    """任务对外视图（不含 result 大字段与文件路径）。"""
    has_result = bool(job.get("result"))
    return {
        "id": job["id"],
        "original_name": job["original_name"],
        "provider": job["provider"],
        "status": job["status"],
        "progress": round(job["progress"] or 0, 1),
        "message": job["message"] or "",
        "error": job["error"],
        "duration": job["duration"],
        "has_result": has_result,
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


def create_app(config: Config = None) -> Flask:
    config = config or Config()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.max_upload_mb * 1024 * 1024
    app.config["APP_CONFIG"] = config
    CORS(app, origins=config.cors_origins)

    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    store = JobStore(config.database_path)
    providers = build_providers(config)
    manager = JobManager(config, store, providers)
    manager.recover()
    app.extensions["store"] = store
    app.extensions["manager"] = manager

    # ---- 错误处理 ----

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"error": f"文件超过上传限制（{config.max_upload_mb}MB）"}), 413

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "接口不存在"}), 404
        return e

    # ---- 配置 ----

    @app.get("/api/config")
    def api_config():
        return jsonify({
            "max_upload_mb": config.max_upload_mb,
            "providers": provider_info(config),
        })

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True})

    # ---- 任务 ----

    @app.post("/api/transcriptions")
    def create_transcription():
        file = request.files.get("file")
        if file is None or not file.filename:
            return jsonify({"error": "请选择要上传的视频文件"}), 400
        provider_id = (request.form.get("provider") or "").strip()
        if provider_id not in providers:
            return jsonify({"error": f"转写服务商不可用: {provider_id}（请检查密钥配置）"}), 400

        options = {}
        raw_options = request.form.get("options")
        if raw_options:
            try:
                options = json.loads(raw_options)
            except json.JSONDecodeError:
                return jsonify({"error": "options 参数不是合法 JSON"}), 400
            if not isinstance(options, dict):
                return jsonify({"error": "options 必须是 JSON 对象"}), 400

        original_name = Path(file.filename).name
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTS:
            return jsonify({"error": f"不支持的视频格式: {ext or '无扩展名'}"}), 400

        job_id = uuid.uuid4().hex
        job_dir = config.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        video_filename = f"source{ext}"
        video_path = job_dir / video_filename
        file.save(video_path)

        try:
            meta = media.probe(video_path)
            if not meta["has_audio"]:
                raise media.MediaError("视频中没有音轨")
        except media.MediaError as e:
            shutil.rmtree(job_dir, ignore_errors=True)
            return jsonify({"error": f"无法读取视频文件: {e}"}), 400

        job = store.create(
            id=job_id,
            original_name=original_name,
            provider=provider_id,
            options=json.dumps(options, ensure_ascii=False),
            video_filename=video_filename,
            audio_filename="audio.wav",
            duration=round(meta["duration"], 2) if meta["duration"] else None,
        )
        manager.submit(job_id)
        return jsonify(_public(job)), 202

    @app.get("/api/transcriptions")
    def list_transcriptions():
        try:
            limit = max(1, min(200, int(request.args.get("limit", 50))))
        except ValueError:
            limit = 50
        return jsonify([_public(j) for j in store.list(limit=limit)])

    @app.get("/api/transcriptions/<job_id>")
    def get_transcription(job_id):
        job = store.get(job_id)
        if job is None:
            return jsonify({"error": "任务不存在"}), 404
        return jsonify(_public(job))

    @app.get("/api/transcriptions/<job_id>/result")
    def get_result(job_id):
        job = store.get(job_id)
        if job is None:
            return jsonify({"error": "任务不存在"}), 404
        if job["status"] != "completed":
            return jsonify({"error": f"转写尚未完成（当前状态: {job['status']}）"}), 409
        result = json.loads(job["result"] or "{}")
        result["id"] = job_id
        result["count"] = len(result.get("segments") or [])
        return jsonify(result)

    @app.get("/api/transcriptions/<job_id>/export")
    def export_transcription(job_id):
        job = store.get(job_id)
        if job is None:
            return jsonify({"error": "任务不存在"}), 404
        if job["status"] != "completed":
            return jsonify({"error": "转写尚未完成"}), 409
        fmt = request.args.get("format", "srt").lower()
        if fmt not in EXPORT_FORMATS:
            return jsonify({"error": f"不支持的导出格式: {fmt}"}), 400
        result = json.loads(job["result"] or "{}")
        content = EXPORT_FORMATS[fmt](result.get("segments") or [])
        stem = (Path(job["original_name"]).stem or "transcript")
        stem = stem.replace("\r", "").replace("\n", "")[:100]
        # HTTP 头只能是 latin-1；中文文件名用 RFC 5987 的 filename* 传递
        ascii_stem = "".join(
            c if c.isascii() and (c.isalnum() or c in "-_") else "_" for c in stem
        ).strip("_") or "transcript"
        encoded_name = quote(f"{stem}.{fmt}")
        resp = app.response_class(content, mimetype="text/plain")
        resp.headers["Content-Disposition"] = (
            f"attachment; filename=\"{ascii_stem}.{fmt}\"; "
            f"filename*=UTF-8''{encoded_name}"
        )
        return resp

    @app.get("/api/transcriptions/<job_id>/video")
    def get_video(job_id):
        job = store.get(job_id)
        if job is None:
            return jsonify({"error": "任务不存在"}), 404
        video_path = config.job_dir(job_id) / job["video_filename"]
        if not video_path.is_file():
            return jsonify({"error": "视频文件不存在"}), 404
        mimetype = mimetypes.guess_type(job["video_filename"])[0] or "application/octet-stream"
        # conditional=True 支持 Range 请求，前端 video 标签拖动进度条依赖它
        return send_file(video_path, mimetype=mimetype, conditional=True)

    @app.post("/api/transcriptions/<job_id>/retry")
    def retry_transcription(job_id):
        job = store.get(job_id)
        if job is None:
            return jsonify({"error": "任务不存在"}), 404
        if job["status"] in ("pending", "extracting", "transcribing"):
            return jsonify({"error": "任务正在处理中，无法重试"}), 409
        if job["status"] == "completed":
            return jsonify({"error": "任务已完成，无需重试"}), 409
        if job["provider"] not in providers:
            return jsonify({"error": "原转写服务商当前不可用，请检查密钥配置"}), 400
        video_path = config.job_dir(job_id) / job["video_filename"]
        if not video_path.is_file():
            return jsonify({"error": "原始视频文件已丢失，请重新上传"}), 400

        store.update(
            job_id, status="pending", progress=0, message="排队中",
            error=None, result=None,
        )
        manager.submit(job_id)
        return jsonify(_public(store.get(job_id))), 202

    @app.delete("/api/transcriptions/<job_id>")
    def delete_transcription(job_id):
        if store.get(job_id) is None:
            return jsonify({"error": "任务不存在"}), 404
        manager.delete_job(job_id)
        return jsonify({"ok": True})

    # ---- 前端静态文件（生产模式：npm run build 后由 Flask 直接托管） ----

    dist_dir = config.project_dir / "frontend" / "dist"
    if dist_dir.is_dir():
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def spa(path):
            if path.startswith("api/"):
                return jsonify({"error": "接口不存在"}), 404
            target = safe_join(str(dist_dir), path)
            if target and Path(target).is_file():
                return send_file(target)
            return send_from_directory(dist_dir, "index.html")

    return app


if __name__ == "__main__":
    _config = Config()
    _app = create_app(_config)
    _app.run(host=_config.host, port=_config.port, debug=_config.debug, threaded=True)
