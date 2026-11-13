"""SQLite 任务持久化：单表保存完整任务 JSON，内存只做缓存。

设计说明：
- 表结构与任务字段解耦，payload 存完整 JSON，后续加字段无需迁移；
- 每次写入使用独立连接 + WAL，适合 Web 单进程/少量并发；
- 支持从旧版 `output/web_tasks/*.json` 导入，平滑迁移。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path


class TaskStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
                )
                conn.commit()
            finally:
                conn.close()

    def upsert(self, task: dict) -> None:
        task_id = str(task.get("id") or "")
        if not task_id:
            raise ValueError("任务缺少 id")
        now = time.time()
        payload = json.dumps(task, ensure_ascii=False)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO tasks(id, status, created_at, updated_at, payload)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        status = excluded.status,
                        updated_at = excluded.updated_at,
                        payload = excluded.payload
                    """,
                    (
                        task_id,
                        str(task.get("status") or "queued"),
                        float(task.get("created_at") or now),
                        now,
                        payload,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def delete(self, task_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM tasks WHERE id = ?", (str(task_id),))
                conn.commit()
            finally:
                conn.close()

    def load_all(self, limit: int = 500) -> list[dict]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT payload FROM tasks ORDER BY created_at DESC LIMIT ?",
                    (max(1, int(limit)),),
                ).fetchall()
            finally:
                conn.close()

        tasks: list[dict] = []
        for (payload,) in rows:
            try:
                task = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(task, dict) and task.get("id"):
                tasks.append(task)
        return tasks

    def import_json_dir(
        self,
        directory: Path,
        existing_ids: set[str] | None = None,
    ) -> int:
        """把旧版 web_tasks JSON 导入 SQLite，返回导入数量。"""
        directory = Path(directory)
        if not directory.exists():
            return 0
        existing_ids = set(existing_ids or [])
        imported = 0
        for path in sorted(directory.glob("*.json")):
            try:
                task = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(task, dict) or not task.get("id"):
                continue
            task_id = str(task["id"])
            if task_id in existing_ids:
                continue
            try:
                self.upsert(task)
            except Exception:
                continue
            existing_ids.add(task_id)
            imported += 1
        return imported
