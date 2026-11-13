"""Web 工作台接口测试：只测上传、校验与干跑，不调用真实模型。"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

import app as webapp
from core.cost import CostLedger
from core.pipeline import Plan


class WebApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(webapp.app)
        cls.sample_png = (ROOT / "assets" / "models" / "02.png").read_bytes()
        cls.uploaded: list[str] = []

    @classmethod
    def tearDownClass(cls):
        for name in cls.uploaded:
            (webapp.UPLOAD_DIR / name).unlink(missing_ok=True)

    def _upload(self, data: bytes, name: str = "model.png", mime: str = "image/png") -> dict:
        response = self.client.post("/api/upload", files={"file": (name, data, mime)})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.uploaded.append(payload["asset_id"])
        return payload

    def test_index_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("衣镜 Studio", response.text)
        self.assertIn("/static/app.js", response.text)

    def test_config_does_not_leak_key(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("edit_model", payload)
        self.assertNotIn("dashscope_api_key", payload)
        self.assertNotIn("api_key", {key.lower() for key in payload})
        self.assertTrue(payload["models"])
        self.assertTrue(all("price" in item for item in payload["models"]))
        self.assertEqual(payload["currency"], "CNY")
        self.assertIn("ark_configured", payload)
        self.assertTrue(payload["tryon_models"])
        self.assertTrue(payload["tryon_methods"])
        self.assertFalse(payload["balance_ui_enabled"])

    def test_upload_and_fetch_asset(self):
        payload = self._upload(self.sample_png)
        self.assertTrue(payload["asset_id"].endswith(".png"))
        fetched = self.client.get(payload["url"])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.headers["content-type"], "image/png")
        self.assertEqual(fetched.content, self.sample_png)

    def test_upload_rejects_fake_image(self):
        response = self.client.post(
            "/api/upload",
            files={"file": ("fake.png", b"not an image", "image/png")},
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_rejects_unknown_suffix(self):
        response = self.client.post(
            "/api/upload",
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)

    def test_dry_run_returns_prompt_without_api(self):
        asset = self._upload(self.sample_png)
        response = self.client.post(
            "/api/restyle",
            json={
                "image_id": asset["asset_id"],
                "instruction": "把上装换成米白色针织开衫",
                "part": "top",
                "count": 1,
                "dry_run": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "dry_run")
        self.assertIn("米白色针织开衫", payload["prompt"])
        self.assertIn("背景完全不变", payload["prompt"])
        self.assertTrue(payload["model"])
        self.assertEqual(len(payload["references"]), 1)
        self.assertIn("cost", payload)
        self.assertEqual(payload["cost"]["currency"], "CNY")
        self.assertIsNotNone(payload["cost"]["estimated"])

    def test_dry_run_rejects_unknown_model(self):
        asset = self._upload(self.sample_png)
        response = self.client.post(
            "/api/restyle",
            json={
                "image_id": asset["asset_id"],
                "instruction": "换成米色针织开衫",
                "model": "not-a-real-model",
                "dry_run": True,
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_dry_run_requires_instruction_or_garment(self):
        asset = self._upload(self.sample_png)
        response = self.client.post(
            "/api/restyle",
            json={"image_id": asset["asset_id"], "part": "top", "dry_run": True},
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_task_returns_404(self):
        response = self.client.get("/api/tasks/task_does_not_exist")
        self.assertEqual(response.status_code, 404)

    def test_sse_stream_ends_on_terminal_status(self):
        task_id = "task_test_sse"
        with webapp._tasks_lock:
            webapp._tasks[task_id] = {
                "id": task_id,
                "status": "succeeded",
                "images": [],
                "elapsed_ms": 1234,
                "cost": {"amount": 0.5, "currency": "CNY"},
            }
        try:
            response = self.client.get(f"/api/tasks/{task_id}/events")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
            self.assertIn("data: ", response.text)
            self.assertIn('"status": "succeeded"', response.text)
        finally:
            with webapp._tasks_lock:
                webapp._tasks.pop(task_id, None)

    def test_run_task_records_cost_and_ledger(self):
        plan = Plan(action="restyle", method="qwen-image-edit", part="top", prompt="test prompt")
        plan.details = {"used_model": "qwen-image-3.0"}
        record = {"path": str(ROOT / "assets" / "models" / "02.png"), "url": None}

        original = (webapp.run_restyle, webapp._file_url, webapp.ledger, webapp._save_task)
        task_id = "task_test_run"
        with tempfile.TemporaryDirectory() as tmp:
            webapp.run_restyle = lambda **kwargs: ([plan], [record])
            webapp._file_url = lambda path: "/files/fake.png"
            webapp.ledger = CostLedger(Path(tmp) / "ledger.jsonl")
            webapp._save_task = lambda task: None
            with webapp._tasks_lock:
                webapp._tasks[task_id] = {
                    "id": task_id,
                    "status": "queued",
                    "cost": {"estimated": 0.5, "currency": "CNY"},
                }
            try:
                webapp._run_task(
                    task_id,
                    "restyle",
                    {
                        "image": "img.jpg",
                        "instructions": ["换成米色"],
                        "garment": None,
                        "part": "top",
                        "count": 1,
                        "size": None,
                        "model": None,
                    },
                )
                task = webapp._tasks[task_id]
                self.assertEqual(task["status"], "succeeded")
                self.assertEqual(task["cost"]["amount"], 0.5)
                self.assertEqual(task["images"][0]["url"], "/files/fake.png")
                self.assertIn("elapsed_ms", task)

                entries = webapp.ledger.entries()
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]["status"], "succeeded")
                self.assertEqual(entries[0]["amount"], 0.5)
                self.assertEqual(entries[0]["model"], "qwen-image-3.0")
            finally:
                webapp.run_restyle, webapp._file_url, webapp.ledger, webapp._save_task = original
                with webapp._tasks_lock:
                    webapp._tasks.pop(task_id, None)

    def test_dry_run_tryon(self):
        person = self._upload(self.sample_png)
        garment = self._upload(self.sample_png)
        response = self.client.post(
            "/api/tryon",
            json={
                "person_image_id": person["asset_id"],
                "garment_id": garment["asset_id"],
                "part": "top",
                "method": "qwen",
                "variants": 2,
                "size": "2K",
                "dry_run": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(payload["method"], "qwen")
        self.assertEqual(payload["model"], webapp.settings.tryon_model)
        if webapp.settings.tryon_engine == "edit":
            self.assertEqual(payload["engine"], "edit")
            self.assertIn("图2是目标上装", payload["prompt"])
        else:
            self.assertIn("full body", payload["prompt"])
        self.assertEqual(payload["cost"]["unit"], 0.5)
        self.assertEqual(payload["cost"]["estimated"], 1.0)
        self.assertEqual(len(payload["references"]), 2)

    def test_tryon_full_requires_bottom(self):
        person = self._upload(self.sample_png)
        garment = self._upload(self.sample_png)
        response = self.client.post(
            "/api/tryon",
            json={
                "person_image_id": person["asset_id"],
                "garment_id": garment["asset_id"],
                "part": "full",
                "dry_run": True,
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_tryon_rejects_unknown_method(self):
        person = self._upload(self.sample_png)
        garment = self._upload(self.sample_png)
        response = self.client.post(
            "/api/tryon",
            json={
                "person_image_id": person["asset_id"],
                "garment_id": garment["asset_id"],
                "method": "magic",
                "dry_run": True,
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_run_task_tryon_records_cost(self):
        plan = Plan(action="tryon", method="qwen", part="top", prompt="tryon prompt")
        record = {"path": str(ROOT / "assets" / "models" / "02.png"), "url": None}

        original = (webapp.run_tryon, webapp._file_url, webapp.ledger, webapp._save_task)
        task_id = "task_test_tryon"
        with tempfile.TemporaryDirectory() as tmp:
            webapp.run_tryon = lambda **kwargs: (plan, [record])
            webapp._file_url = lambda path: "/files/fake-tryon.png"
            webapp.ledger = CostLedger(Path(tmp) / "ledger.jsonl")
            webapp._save_task = lambda task: None
            with webapp._tasks_lock:
                webapp._tasks[task_id] = {
                    "id": task_id,
                    "status": "queued",
                    "cost": {"estimated": 1.0, "currency": "CNY"},
                }
            try:
                webapp._run_task(
                    task_id,
                    "tryon",
                    {
                        "garment": "g.jpg",
                        "model": "p.jpg",
                        "bottom_garment": None,
                        "part": "top",
                        "variants": 1,
                        "method": "qwen",
                        "size": "2K",
                    },
                )
                task = webapp._tasks[task_id]
                self.assertEqual(task["status"], "succeeded")
                self.assertEqual(task["used_model"], webapp.settings.tryon_model)
                self.assertEqual(task["cost"]["amount"], 0.5)
                entries = webapp.ledger.entries()
                self.assertEqual(entries[0]["action"], "tryon")
                self.assertEqual(entries[0]["model"], webapp.settings.tryon_model)
            finally:
                webapp.run_tryon, webapp._file_url, webapp.ledger, webapp._save_task = original
                with webapp._tasks_lock:
                    webapp._tasks.pop(task_id, None)

    def _add_fake_history_task(self, task_id: str, tmp: Path, count: int = 2) -> dict:
        session_dir = tmp / "task_test" / "step6_restyle"
        session_dir.mkdir(parents=True, exist_ok=True)
        images = []
        for index in range(count):
            path = session_dir / f"result_{index}.png"
            path.write_bytes(self.sample_png)
            images.append({
                "url": f"/files/task_test/step6_restyle/result_{index}.png",
                "name": f"result_{index}.png",
            })
        task = {
            "id": task_id,
            "type": "restyle",
            "status": "succeeded",
            "created_at": 1700000000 + len(webapp._tasks),
            "elapsed_ms": 1000,
            "used_model": "qwen-image-3.0",
            "cost": {"amount": 0.5, "currency": "CNY"},
            "request": {"instruction": "换成米色针织开衫", "has_garment": False},
            "images": images,
        }
        with webapp._tasks_lock:
            webapp._tasks[task_id] = task
        return task

    def test_history_listing_and_delete_image(self):
        task_id = "task_test_history_img"
        original_settings = webapp.settings
        original_save = webapp._save_task
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            task = self._add_fake_history_task(task_id, tmp_path)
            webapp.settings = replace(original_settings, output_dir=tmp_path)
            webapp._save_task = lambda task: None
            try:
                listing = self.client.get("/api/history").json()
                item = next(item for item in listing if item["id"] == task_id)
                self.assertEqual(item["image_count"], 2)
                self.assertEqual(item["title"], "换成米色针织开衫")
                self.assertTrue(item["images"][0]["thumb_url"].startswith("/thumb/"))

                thumb = self.client.get(item["images"][0]["thumb_url"])
                self.assertEqual(thumb.status_code, 200, thumb.text)
                self.assertEqual(thumb.headers["content-type"], "image/jpeg")
                self.assertTrue(thumb.content.startswith(b"\xff\xd8\xff"))

                response = self.client.delete(f"/api/history/{task_id}/images/0")
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertTrue(payload["deleted_file"])
                self.assertEqual(payload["remaining"], 1)
                self.assertFalse(
                    (tmp_path / "task_test" / "step6_restyle" / "result_0.png").exists()
                )
                self.assertTrue(
                    (tmp_path / "task_test" / "step6_restyle" / "result_1.png").exists()
                )
                self.assertEqual(len(task["images"]), 1)
                self.assertFalse(payload["removed_task"])
            finally:
                webapp.settings = original_settings
                webapp._save_task = original_save
                with webapp._tasks_lock:
                    webapp._tasks.pop(task_id, None)

    def test_history_delete_whole_task(self):
        task_id = "task_test_history_all"
        original_settings = webapp.settings
        original_save = webapp._save_task
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._add_fake_history_task(task_id, tmp_path, count=2)
            webapp.settings = replace(original_settings, output_dir=tmp_path)
            webapp._save_task = lambda task: None
            try:
                response = self.client.delete(f"/api/history/{task_id}")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["deleted_images"], 2)
                self.assertNotIn(task_id, webapp._tasks)
                self.assertFalse(
                    (tmp_path / "task_test" / "step6_restyle" / "result_0.png").exists()
                )
                self.assertFalse(
                    (tmp_path / "task_test" / "step6_restyle" / "result_1.png").exists()
                )
            finally:
                webapp.settings = original_settings
                webapp._save_task = original_save
                with webapp._tasks_lock:
                    webapp._tasks.pop(task_id, None)

    def test_history_delete_rejects_running_task(self):
        task_id = "task_test_history_running"
        with webapp._tasks_lock:
            webapp._tasks[task_id] = {"id": task_id, "status": "running", "images": []}
        try:
            response = self.client.delete(f"/api/history/{task_id}")
            self.assertEqual(response.status_code, 409)
        finally:
            with webapp._tasks_lock:
                webapp._tasks.pop(task_id, None)

    def test_balance_config_save_and_clear(self):
        original = (
            webapp.ENV_PATH,
            webapp.settings,
            os.environ.get("ALIYUN_ACCESS_KEY_ID"),
            os.environ.get("ALIYUN_ACCESS_KEY_SECRET"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("DASHSCOPE_API_KEY=sk-existing\n", encoding="utf-8")
            webapp.ENV_PATH = env_path
            webapp.settings = replace(
                webapp.settings,
                aliyun_access_key_id="",
                aliyun_access_key_secret="",
            )
            try:
                response = self.client.post(
                    "/api/balance/config",
                    json={
                        "access_key_id": "LTAI5tExampleKey123",
                        "access_key_secret": "ExampleSecret1234567890",
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertTrue(payload["saved"])
                self.assertEqual(payload["access_key_id_masked"], "LTAI****y123")
                self.assertNotIn("ExampleSecret", response.text)

                content = env_path.read_text(encoding="utf-8")
                self.assertIn("DASHSCOPE_API_KEY=sk-existing", content)
                self.assertIn("ALIYUN_ACCESS_KEY_ID=LTAI5tExampleKey123", content)
                self.assertIn("ALIYUN_ACCESS_KEY_SECRET=ExampleSecret1234567890", content)
                self.assertEqual(
                    webapp.settings.aliyun_access_key_id, "LTAI5tExampleKey123"
                )

                cleared = self.client.delete("/api/balance/config")
                self.assertEqual(cleared.status_code, 200)
                self.assertTrue(cleared.json()["cleared"])
                content = env_path.read_text(encoding="utf-8")
                self.assertIn("ALIYUN_ACCESS_KEY_ID=\n", content)
                self.assertIn("ALIYUN_ACCESS_KEY_SECRET=\n", content)
                self.assertEqual(webapp.settings.aliyun_access_key_id, "")
            finally:
                (
                    webapp.ENV_PATH,
                    webapp.settings,
                    env_id,
                    env_secret,
                ) = original
                if env_id is None:
                    os.environ.pop("ALIYUN_ACCESS_KEY_ID", None)
                else:
                    os.environ["ALIYUN_ACCESS_KEY_ID"] = env_id
                if env_secret is None:
                    os.environ.pop("ALIYUN_ACCESS_KEY_SECRET", None)
                else:
                    os.environ["ALIYUN_ACCESS_KEY_SECRET"] = env_secret

    def test_balance_config_requires_secret(self):
        response = self.client.post(
            "/api/balance/config",
            json={"access_key_id": "LTAI5tExampleKey123", "access_key_secret": ""},
        )
        self.assertEqual(response.status_code, 400)

    def test_balance_endpoint_without_access_key(self):
        response = self.client.get("/api/balance")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("available", payload)
        self.assertIn("cost_summary", payload)
        self.assertIn("currency", payload["cost_summary"])
        self.assertIn("dashscope_key_configured", payload)
        self.assertNotIn("aliyun_access_key_secret", payload)
        self.assertNotIn("aliyun_access_key_id", payload)

    def test_models_library(self):
        response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200, response.text)
        models = response.json()
        self.assertEqual(len(models), 45)
        self.assertNotIn("local", models[0])
        self.assertTrue(models[0]["image_url"].startswith("/api/models/"))
        self.assertTrue(models[0]["name"])

        image = self.client.get(models[0]["image_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["content-type"], "image/png")
        self.assertGreater(len(image.content), 1000)

        missing = self.client.get("/api/models/not-a-model/image")
        self.assertEqual(missing.status_code, 404)

    def test_video_dry_run(self):
        asset = self._upload(self.sample_png)
        response = self.client.post(
            "/api/video",
            json={
                "image_id": asset["asset_id"],
                "prompt": "模特自然缓慢转身，展示服装全貌",
                "duration": 5,
                "resolution": "480P",
                "method": "wan",
                "dry_run": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(payload["method"], "wan-i2v")
        self.assertEqual(payload["model"], webapp.settings.video_model)
        self.assertIn("转身", payload["prompt"])
        self.assertEqual(payload["cost"]["unit"], 0.3)
        self.assertEqual(payload["cost"]["estimated"], 1.5)
        self.assertEqual(payload["cost"]["unit_type"], "second")

    def test_video_rejects_bad_duration_and_resolution(self):
        asset = self._upload(self.sample_png)
        bad_duration = self.client.post(
            "/api/video",
            json={"image_id": asset["asset_id"], "duration": 7, "dry_run": True},
        )
        self.assertEqual(bad_duration.status_code, 400)
        bad_resolution = self.client.post(
            "/api/video",
            json={"image_id": asset["asset_id"], "resolution": "8K", "dry_run": True},
        )
        self.assertEqual(bad_resolution.status_code, 400)

    def test_run_task_video_records_cost(self):
        plan = Plan(action="video", method="wan-i2v", part="video", prompt="video prompt")
        plan.details = {"model": "wan2.5-i2v-preview"}
        original = (webapp.run_video, webapp._file_url, webapp.ledger, webapp._save_task,
                    webapp.settings)
        task_id = "task_test_video"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_file = tmp_path / "task_test" / "video.mp4"
            video_file.parent.mkdir(parents=True, exist_ok=True)
            video_file.write_bytes(b"\x00" * 60 * 1024)
            record = {"path": str(video_file), "url": None}
            webapp.run_video = lambda **kwargs: (plan, [record])
            webapp._file_url = lambda path: "/files/task_test/video.mp4"
            webapp.ledger = CostLedger(tmp_path / "ledger.jsonl")
            webapp._save_task = lambda task: None
            webapp.settings = replace(original[4], output_dir=tmp_path)
            with webapp._tasks_lock:
                webapp._tasks[task_id] = {
                    "id": task_id,
                    "type": "video",
                    "status": "queued",
                    "cost": {"estimated": 1.5, "currency": "CNY"},
                    "images": [],
                }
            try:
                webapp._run_task(
                    task_id,
                    "video",
                    {
                        "image": "frame.png",
                        "prompt": "转身",
                        "duration": 5,
                        "resolution": "480P",
                        "method": "wan",
                    },
                )
                task = webapp._tasks[task_id]
                self.assertEqual(task["status"], "succeeded")
                self.assertEqual(task["video"]["url"], "/files/task_test/video.mp4")
                self.assertEqual(task["cost"]["unit"], 0.3)
                self.assertEqual(task["cost"]["amount"], 1.5)
                entries = webapp.ledger.entries()
                self.assertEqual(entries[0]["action"], "video")
                self.assertEqual(entries[0]["amount"], 1.5)
                self.assertEqual(entries[0]["model"], "wan2.5-i2v-preview")
            finally:
                (webapp.run_video, webapp._file_url, webapp.ledger,
                 webapp._save_task, webapp.settings) = original
                with webapp._tasks_lock:
                    webapp._tasks.pop(task_id, None)

    def test_history_includes_video_task(self):
        task_id = "task_test_history_video"
        with webapp._tasks_lock:
            webapp._tasks[task_id] = {
                "id": task_id,
                "type": "video",
                "status": "succeeded",
                "created_at": 1700000000,
                "used_model": "wan2.5-i2v-preview",
                "request": {"prompt": "模特转身", "duration": 5, "resolution": "480P"},
                "cost": {"amount": 1.5, "currency": "CNY"},
                "images": [],
                "video": {"url": "/files/task_test/video.mp4", "name": "video.mp4"},
                "image_url": "/api/asset/frame.png",
            }
        try:
            listing = self.client.get("/api/history").json()
            item = next(entry for entry in listing if entry["id"] == task_id)
            self.assertEqual(item["type"], "video")
            self.assertEqual(item["title"], "模特转身")
            self.assertEqual(item["video"]["url"], "/files/task_test/video.mp4")
            self.assertEqual(item["image_count"], 0)
            self.assertEqual(item["duration"], 5)
        finally:
            with webapp._tasks_lock:
                webapp._tasks.pop(task_id, None)

    def test_stylist_endpoint(self):
        original = webapp.generate_schemes
        webapp.generate_schemes = lambda settings, **kwargs: {
            "schemes": [
                {
                    "id": "look_1",
                    "title": "测试方案",
                    "item_ids": ["W01", "W07"],
                    "items": [
                        {"id": "W01", "name": "白色棉质衬衫", "category": "上装",
                         "color": "白色", "style": "通勤"},
                    ],
                    "colors": ["白色"],
                    "reason": "适合通勤",
                    "tips": ["要点一"],
                    "instruction": "测试指令",
                    "anchor": "",
                }
            ],
            "model": "test-model",
            "generated_by": "llm",
        }
        try:
            response = self.client.post(
                "/api/stylist",
                json={"occasion": "通勤", "season": "四季", "palette": "中性"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(len(payload["schemes"]), 1)
            self.assertEqual(payload["model"], "test-model")
            self.assertEqual(payload["options"]["occasions"][0], "通勤")
        finally:
            webapp.generate_schemes = original

    def test_stylist_rejects_unknown_option(self):
        response = self.client.post(
            "/api/stylist", json={"occasion": "不存在的场合"}
        )
        self.assertEqual(response.status_code, 400)

    def test_lookbook_zip_export(self):
        task_id = "task_test_lookbook"
        original_settings = webapp.settings
        original_save = webapp._save_task
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._add_fake_history_task(task_id, tmp_path, count=1)
            webapp.settings = replace(original_settings, output_dir=tmp_path)
            webapp._save_task = lambda task: None
            try:
                response = self.client.get(f"/api/lookbook/{task_id}")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.content.startswith(b"PK"))

                with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                    names = archive.namelist()
                    prefix = f"lookbook_{task_id}/"
                    self.assertIn(prefix + "lookbook.md", names)
                    self.assertIn(prefix + "manifest.json", names)
                    self.assertTrue(any(name.endswith("01_main_3x4.jpg") for name in names))
                    self.assertTrue(any(name.endswith("01_detail_1x1.jpg") for name in names))
                    self.assertTrue(any(name.endswith("01_original.png") for name in names))

                    markdown = archive.read(prefix + "lookbook.md").decode("utf-8")
                    self.assertIn("换成米色针织开衫", markdown)
                    self.assertIn("成本清单", markdown)
                    self.assertIn("场景建议", markdown)

                    manifest = json.loads(archive.read(prefix + "manifest.json"))
                    self.assertEqual(manifest["task_id"], task_id)
                    self.assertEqual(manifest["image_count"], 1)
            finally:
                webapp.settings = original_settings
                webapp._save_task = original_save
                with webapp._tasks_lock:
                    webapp._tasks.pop(task_id, None)

    def test_costs_endpoint_shape(self):
        response = self.client.get("/api/costs")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["currency"], "CNY")
        for key in ("total_amount", "total_images", "calls", "by_model", "recent"):
            self.assertIn(key, payload)

    def test_file_endpoint_blocks_traversal(self):
        response = self.client.get("/files/../config.py")
        self.assertIn(response.status_code, {403, 404})


if __name__ == "__main__":
    unittest.main(verbosity=2)
