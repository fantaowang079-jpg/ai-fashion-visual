"""SQLite 任务持久化测试。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.taskstore import TaskStore


def make_task(task_id: str, created_at: float = 1000.0, status: str = "succeeded") -> dict:
    return {
        "id": task_id,
        "type": "tryon",
        "status": status,
        "created_at": created_at,
        "request": {"part": "top", "desc": "白色衬衫"},
        "images": [{"url": f"/files/{task_id}/01.png", "name": "01.png"}],
        "cost": {"amount": 0.5, "currency": "CNY"},
    }


class TaskStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "tasks.db"
        self.store = TaskStore(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_upsert_and_load_roundtrip(self):
        task = make_task("task_a", 1000.0)
        self.store.upsert(task)
        loaded = self.store.load_all()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["id"], "task_a")
        self.assertEqual(loaded[0]["request"]["desc"], "白色衬衫")
        self.assertEqual(loaded[0]["images"][0]["url"], "/files/task_a/01.png")
        self.assertTrue(self.db_path.exists())

    def test_update_keeps_single_row(self):
        self.store.upsert(make_task("task_a", 1000.0, "queued"))
        updated = make_task("task_a", 1000.0, "succeeded")
        updated["images"] = []
        self.store.upsert(updated)
        loaded = self.store.load_all()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["status"], "succeeded")
        self.assertEqual(loaded[0]["images"], [])

    def test_ordering_and_limit(self):
        self.store.upsert(make_task("task_old", 1000.0))
        self.store.upsert(make_task("task_new", 2000.0))
        loaded = self.store.load_all()
        self.assertEqual([task["id"] for task in loaded], ["task_new", "task_old"])
        self.assertEqual(len(self.store.load_all(limit=1)), 1)

    def test_delete(self):
        self.store.upsert(make_task("task_a"))
        self.store.delete("task_a")
        self.assertEqual(self.store.load_all(), [])

    def test_import_json_dir_skips_existing(self):
        json_dir = Path(self.tmp.name) / "web_tasks"
        json_dir.mkdir()
        for task_id in ("task_json_1", "task_json_2"):
            (json_dir / f"{task_id}.json").write_text(
                json.dumps(make_task(task_id), ensure_ascii=False), encoding="utf-8"
            )
        self.store.upsert(make_task("task_json_1"))

        imported = self.store.import_json_dir(json_dir, existing_ids={"task_json_1"})
        self.assertEqual(imported, 1)
        ids = {task["id"] for task in self.store.load_all()}
        self.assertEqual(ids, {"task_json_1", "task_json_2"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
