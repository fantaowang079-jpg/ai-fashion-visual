"""Session 输出目录管理：分阶段保存、JSONL 日志、24 小时复用。"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

STAGE_DIRS = {
    "garment": "step1_garment",
    "model": "step2_model",
    "tryon": "step3_tryon",
    "variants": "step4_variants",
    "video": "step5_video",
    "restyle": "step6_restyle",
}


class Session:
    def __init__(self, base_dir: Path, fresh: bool = False):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = self._resolve_session_id(fresh)
        self.dir = self.base_dir / self.session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.dir / "session_log.jsonl"

    def _resolve_session_id(self, fresh: bool) -> str:
        marker = self.base_dir / ".current_session"
        if fresh and marker.exists():
            marker.unlink()
        if marker.exists():
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                created = float(data.get("created_at", 0))
                sid = str(data.get("session_id", ""))
                if sid and time.time() - created < 86400 and (self.base_dir / sid).exists():
                    return sid
            except Exception:
                pass

        sid = dt.datetime.now().strftime("task_%Y%m%d_%H%M%S")
        marker.write_text(
            json.dumps({"session_id": sid, "created_at": time.time()}, ensure_ascii=False),
            encoding="utf-8",
        )
        return sid

    def stage_dir(self, stage: str) -> Path:
        directory = self.dir / STAGE_DIRS.get(stage, stage)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _ts(self) -> str:
        return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

    def _append_log(self, record: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def save_url(self, url: str, stage: str, label: str = "", ext: str = "jpg") -> dict:
        suffix = f"_{label}" if label else ""
        path = self.stage_dir(stage) / f"{stage}{suffix}_{self._ts()}.{ext}"
        urllib.request.urlretrieve(url, path)
        record = {"url": url, "path": str(path.resolve()), "stage": stage, "label": label}
        self._append_log(record)
        return record

    def save_b64(self, b64_data: str, stage: str, label: str = "", ext: str = "png") -> dict:
        import base64

        suffix = f"_{label}" if label else ""
        path = self.stage_dir(stage) / f"{stage}{suffix}_{self._ts()}.{ext}"
        path.write_bytes(base64.b64decode(b64_data))
        record = {"url": None, "path": str(path.resolve()), "stage": stage, "label": label}
        self._append_log(record)
        return record

    def save_video_url(self, url: str, label: str = "i2v") -> dict:
        record = self.save_url(url, stage="video", label=label, ext="mp4")
        if Path(record["path"]).stat().st_size < 50 * 1024:
            Path(record["path"]).unlink(missing_ok=True)
            raise RuntimeError("视频文件异常（小于 50KB），可能是 API 错误页而非真实视频")
        return record

    def log_generation(self, **kwargs) -> None:
        record = {"stage": "meta", **kwargs}
        self._append_log(record)

    def list_images(self, stages: tuple[str, ...] = ("tryon", "variants")) -> list[str]:
        exts = {".jpg", ".jpeg", ".png", ".webp"}
        images: list[str] = []
        for stage in stages:
            directory = self.dir / STAGE_DIRS.get(stage, stage)
            if not directory.exists():
                continue
            for path in sorted(directory.iterdir()):
                if path.suffix.lower() in exts:
                    images.append(str(path.resolve()))
        return images
