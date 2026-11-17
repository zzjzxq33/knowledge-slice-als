"""SQLite 任务存储。每次操作使用独立连接，线程安全。"""
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _write(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            conn = self._connect()
            try:
                with conn:  # 事务提交
                    conn.execute(sql, params)
            finally:
                conn.close()

    def _read(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def _init(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS jobs (
                            id             TEXT PRIMARY KEY,
                            original_name  TEXT NOT NULL,
                            provider       TEXT NOT NULL,
                            options        TEXT NOT NULL DEFAULT '{}',
                            status         TEXT NOT NULL DEFAULT 'pending',
                            progress       REAL NOT NULL DEFAULT 0,
                            message        TEXT NOT NULL DEFAULT '',
                            error          TEXT,
                            duration       REAL,
                            video_filename TEXT,
                            audio_filename TEXT,
                            result         TEXT,
                            created_at     TEXT NOT NULL,
                            updated_at     TEXT NOT NULL
                        )
                        """
                    )
            finally:
                conn.close()

    def create(self, id: str, original_name: str, provider: str, options: str,
               video_filename: str, audio_filename: str, duration=None) -> dict:
        now = utcnow_iso()
        self._write(
            "INSERT INTO jobs (id, original_name, provider, options, status, "
            "video_filename, audio_filename, duration, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
            (id, original_name, provider, options, video_filename, audio_filename,
             duration, now, now),
        )
        return self.get(id)

    def update(self, job_id: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = utcnow_iso()
        keys = ", ".join(f"{k} = ?" for k in fields)
        self._write(f"UPDATE jobs SET {keys} WHERE id = ?", (*fields.values(), job_id))

    def get(self, job_id: str) -> dict | None:
        rows = self._read("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return rows[0] if rows else None

    def list(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self._read(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
        )

    def delete(self, job_id: str) -> None:
        self._write("DELETE FROM jobs WHERE id = ?", (job_id,))
