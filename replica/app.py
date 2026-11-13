"""衣镜 Studio · AI 换装 Web 工作台。

启动：
    cd E:\\AI服饰视觉项目\\replica
    python app.py
    浏览器打开 http://127.0.0.1:8000

接口：
    GET  /api/config           Provider 状态与默认模型（不含密钥）
    POST /api/upload           上传人物图 / 服装图
    POST /api/restyle          提交换装任务（支持 dry_run 只预览 Prompt）
    GET  /api/tasks/{id}       查询任务
    GET  /api/tasks/{id}/events  SSE 实时进度
    GET  /api/tasks            最近任务列表
    GET  /api/costs            成本台账汇总
    GET  /api/history          历史记录（已生成图片）
    DELETE /api/history/{id}   删除整条记录及其图片
    DELETE /api/history/{id}/images/{index}  删除单张图片
    GET  /files/{relpath}      读取生成结果
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import ROOT, get_settings
from core.balance import query_account_balance
from core.cost import (
    CURRENCY,
    CostLedger,
    estimate_cost,
    estimate_video_cost,
    load_prices,
    load_video_prices,
)
from core.lookbook import build_lookbook
from core.model_library import get_model_image, load_models
from core.pipeline import VALID_PARTS, run_restyle, run_tryon, run_video
from core.stylist import OCCASIONS, PALETTES, SEASONS, generate_schemes
from core.taskstore import TaskStore
from providers import ProviderError

settings = get_settings()

ENV_PATH = ROOT / ".env"
WEB_DIR = ROOT / "web"
UPLOAD_DIR = ROOT / "uploads"
TASK_DIR = settings.output_dir / "web_tasks"
LEDGER_PATH = settings.output_dir / "cost_ledger.jsonl"
THUMB_DIR = settings.output_dir / ".thumbs"
TASK_DB_PATH = Path(
    os.getenv("TASK_DB_PATH", str(settings.output_dir / "tasks.db"))
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TASK_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)
ledger = CostLedger(LEDGER_PATH)
task_store = TaskStore(TASK_DB_PATH)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

PART_LABELS = {
    "top": "上装",
    "bottom": "下装",
    "one_piece": "连衣裙/连体装",
    "full": "整套上下装",
}

app = FastAPI(title="衣镜 Studio · AI 换装工作台", version="0.1.0")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

# ── 任务存储（SQLite 持久化 + 内存缓存，单 worker 串行执行）──
_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1)


def _save_task(task: dict) -> None:
    """SQLite 为事实来源；同时写 JSON 镜像，便于人工排查与旧版本兼容。"""
    task_id = task.get("id")
    if not task_id:
        return
    try:
        task_store.upsert(task)
    except Exception as exc:
        print(f"[taskstore] SQLite 写入失败 {task_id}: {exc}", file=sys.stderr)
    try:
        path = TASK_DIR / f"{task_id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        print(f"[taskstore] JSON 镜像写入失败 {task_id}: {exc}", file=sys.stderr)


def _load_tasks() -> None:
    """从 SQLite 载入；再导入旧版 JSON 中数据库里没有的任务。"""
    try:
        rows = task_store.load_all(limit=500)
    except Exception as exc:
        print(f"[taskstore] SQLite 读取失败：{exc}", file=sys.stderr)
        rows = []
    for task in rows:
        _tasks[task["id"]] = task

    try:
        imported = task_store.import_json_dir(TASK_DIR, existing_ids=set(_tasks))
    except Exception as exc:
        print(f"[taskstore] JSON 迁移失败：{exc}", file=sys.stderr)
        imported = 0
    if imported:
        for task in task_store.load_all(limit=500):
            _tasks[task["id"]] = task
        print(f"[taskstore] 已从 JSON 迁移 {imported} 条任务到 SQLite", file=sys.stderr)


def _update_task(task_id: str, **fields) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.update(fields)
        _save_task(task)


_load_tasks()


# ── AccessKey 本地配置 ────────────────────────────────────
def _mask_key(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


def _update_env_file(updates: dict[str, str]) -> None:
    path = Path(ENV_PATH)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(updates)
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in pending:
                result.append(f"{key}={pending.pop(key)}")
                continue
        result.append(line)
    for key, value in pending.items():
        result.append(f"{key}={value}")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def _save_balance_credentials(key_id: str, secret: str) -> None:
    """保存到本机 .env，并立即更新内存中的 Settings。"""
    global settings
    _update_env_file(
        {
            "ALIYUN_ACCESS_KEY_ID": key_id,
            "ALIYUN_ACCESS_KEY_SECRET": secret,
        }
    )
    os.environ["ALIYUN_ACCESS_KEY_ID"] = key_id
    os.environ["ALIYUN_ACCESS_KEY_SECRET"] = secret
    settings = replace(
        settings,
        aliyun_access_key_id=key_id,
        aliyun_access_key_secret=secret,
    )


# ── 素材与文件 ────────────────────────────────────────────
def _sniff_ok(data: bytes, suffix: str) -> bool:
    if suffix in {".jpg", ".jpeg"}:
        return data[:3] == b"\xff\xd8\xff"
    if suffix == ".png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if suffix == ".webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if suffix == ".bmp":
        return data[:2] == b"BM"
    return False


def _asset_path(asset_id: str | None) -> Path | None:
    if not asset_id:
        return None
    name = Path(asset_id).name
    path = UPLOAD_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"素材不存在：{name}")
    return path


def _file_url(path_str: str) -> str:
    """把本地输出路径转成 /files/... URL。"""
    path = Path(path_str).resolve()
    base = settings.output_dir.resolve()
    try:
        rel = path.relative_to(base)
    except ValueError:
        return ""
    return "/files/" + rel.as_posix()


def _ensure_thumb(url: str, width: int = 480) -> Path | None:
    """确保 /files/... 对应的缩略图存在，返回缓存路径。"""
    if not url or not url.startswith("/files/"):
        return None
    rel = unquote(url[len("/files/"):])
    base = settings.output_dir.resolve()
    src = (base / rel).resolve()
    if src == base or base not in src.parents or not src.is_file():
        return None
    width = max(120, min(width, 1200))
    cache = (base / ".thumbs" / rel).with_suffix(".jpg")
    if cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime:
        return cache
    try:
        from PIL import Image

        with Image.open(src) as image:
            preview = image.convert("RGB")
            preview.thumbnail((width, int(width * 1.8)), Image.LANCZOS)
            cache.parent.mkdir(parents=True, exist_ok=True)
            preview.save(cache, "JPEG", quality=85, optimize=True)
        return cache
    except Exception:
        return None


def _delete_file_for_url(url: str) -> bool:
    """删除 /files/... 对应的本地文件与缩略图；只允许 output 目录内的路径。"""
    if not url or not url.startswith("/files/"):
        return False
    rel = unquote(url[len("/files/"):])
    base = settings.output_dir.resolve()
    path = (base / rel).resolve()
    if path == base or base not in path.parents:
        return False
    thumb = (base / ".thumbs" / rel).with_suffix(".jpg")
    if thumb.is_file():
        thumb.unlink(missing_ok=True)
    if path.is_file():
        path.unlink()
        return True
    return False


def _history_item(task: dict) -> dict:
    req = task.get("request") or {}
    task_type = task.get("type")
    if task_type == "tryon":
        title = req.get("desc") or f"{PART_LABELS.get(req.get('part'), '服装')}试衣"
    elif task_type == "video":
        title = req.get("prompt") or f"图生视频 · {req.get('resolution', '480P')} {req.get('duration', 5)}s"
    else:
        title = req.get("instruction") or (
            "按服装图换装" if req.get("has_garment") else "AI 换装"
        )
    images = []
    for image in task.get("images") or []:
        item_image = dict(image)
        url = item_image.get("url") or ""
        if url.startswith("/files/"):
            item_image["thumb_url"] = "/thumb/" + url[len("/files/"):]
        images.append(item_image)
    video = task.get("video")
    return {
        "id": task["id"],
        "type": task_type,
        "title": title,
        "status": task.get("status"),
        "created_at": task.get("created_at"),
        "elapsed_ms": task.get("elapsed_ms"),
        "model": task.get("used_model") or task.get("model"),
        "cost": task.get("cost"),
        "images": images,
        "image_count": len(images),
        "video": dict(video) if video else None,
        "image_url": task.get("image_url"),
        "duration": req.get("duration"),
        "resolution": req.get("resolution"),
    }


# ── 请求模型 ──────────────────────────────────────────────
class RestyleRequest(BaseModel):
    image_id: str
    garment_id: str | None = None
    instruction: str | None = None
    part: str = "top"
    count: int = 1
    size: str | None = None
    model: str | None = None
    dry_run: bool = False


class TryonRequest(BaseModel):
    person_image_id: str
    garment_id: str
    bottom_garment_id: str | None = None
    part: str = "top"
    variants: int = 1
    method: str = "auto"
    size: str = "2K"
    desc: str | None = None
    dry_run: bool = False


class StylistRequest(BaseModel):
    occasion: str = "通勤"
    season: str = "四季"
    palette: str = "中性"
    anchor: str | None = None


class VideoRequest(BaseModel):
    image_id: str
    prompt: str | None = None
    duration: int = 5
    resolution: str = "480P"
    method: str = "auto"
    dry_run: bool = False


class BalanceConfigRequest(BaseModel):
    access_key_id: str
    access_key_secret: str


# ── 接口 ─────────────────────────────────────────────────
@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/config")
def api_config() -> dict:
    status = settings.provider_status()
    prices = load_prices()
    model_ids = [settings.qwen_image_edit_model, *settings.qwen_image_edit_fallbacks]
    tryon_models = [settings.tryon_model, settings.ark_image_model]
    return {
        "dashscope_configured": status["dashscope"]["configured"],
        "ark_configured": status["ark"]["configured"],
        "tryon_engine": settings.tryon_engine,
        "edit_model": settings.qwen_image_edit_model,
        "fallbacks": list(settings.qwen_image_edit_fallbacks),
        "models": [
            {"id": model_id, "price": prices.get(model_id), "currency": CURRENCY}
            for model_id in model_ids
        ],
        "tryon_models": [
            {"id": model_id, "price": prices.get(model_id), "currency": CURRENCY}
            for model_id in tryon_models
        ],
        "tryon_method_models": {
            "qwen": settings.tryon_model,
            "seedream": settings.ark_image_model,
        },
        "tryon_methods": [
            {"id": "auto", "available": bool(settings.ark_api_key or settings.dashscope_api_key)},
            {"id": "qwen", "available": bool(settings.dashscope_api_key)},
            {"id": "seedream", "available": bool(settings.ark_api_key)},
        ],
        "currency": CURRENCY,
        "price_note": "单价为估算值，以控制台账单为准",
        "stylist_model": settings.stylist_model,
        "stylist_options": {
            "occasions": OCCASIONS,
            "seasons": SEASONS,
            "palettes": PALETTES,
        },
        "video_model": settings.video_model,
        "video_prices": load_video_prices(),
        "video_resolutions": ["480P", "720P", "1080P"],
        "video_durations": [5, 10],
        "balance_ui_enabled": settings.balance_ui_enabled,
        "parts": ["top", "bottom", "one_piece", "full"],
        "max_count": 4,
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
    }


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="仅支持 JPG / PNG / WEBP / BMP 图片")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="图片超过 10MB，请压缩后再上传")
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    if not _sniff_ok(data, suffix):
        raise HTTPException(status_code=400, detail="文件内容不是有效图片")

    asset_id = f"{uuid.uuid4().hex}{suffix}"
    (UPLOAD_DIR / asset_id).write_bytes(data)
    return {"asset_id": asset_id, "url": f"/api/asset/{asset_id}"}


@app.get("/api/asset/{asset_id}")
def api_asset(asset_id: str) -> FileResponse:
    path = _asset_path(asset_id)
    assert path is not None
    return FileResponse(path, media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"))


@app.post("/api/restyle")
def api_restyle(req: RestyleRequest) -> dict:
    image_path = _asset_path(req.image_id)
    garment_path = _asset_path(req.garment_id)
    instruction = (req.instruction or "").strip() or None

    if not instruction and not garment_path:
        raise HTTPException(status_code=400, detail="请填写换装指令，或上传目标服装图")
    if req.part not in VALID_PARTS:
        raise HTTPException(status_code=400, detail="部位参数不合法")
    if not 1 <= req.count <= 4:
        raise HTTPException(status_code=400, detail="生成数量需在 1~4 之间")
    allowed_models = {settings.qwen_image_edit_model, *settings.qwen_image_edit_fallbacks}
    if req.model and req.model not in allowed_models:
        raise HTTPException(status_code=400, detail=f"不支持的模型：{req.model}")
    if not req.dry_run and not settings.dashscope_api_key:
        raise HTTPException(status_code=503, detail="未配置 DASHSCOPE_API_KEY，无法生成")

    prices = load_prices()
    requested_model = req.model or settings.qwen_image_edit_model
    estimated = estimate_cost(requested_model, req.count, prices)

    # 先做一次干跑：同步校验参数、产出 Prompt 与实际模型
    try:
        plans, _ = run_restyle(
            settings=settings,
            image=str(image_path),
            instructions=[instruction] if instruction else None,
            garment=str(garment_path) if garment_path else None,
            part=req.part,
            count=req.count,
            size=req.size,
            model=req.model,
            dry_run=True,
        )
    except (ValueError, ProviderError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prompt = plans[0].prompt
    model = plans[0].details.get("model")
    references = plans[0].references
    cost = {
        "unit": prices.get(requested_model),
        "estimated": estimated,
        "amount": None,
        "currency": CURRENCY,
    }

    if req.dry_run:
        return {
            "status": "dry_run",
            "prompt": prompt,
            "model": model,
            "references": references,
            "cost": cost,
        }

    task = {
        "id": f"task_{uuid.uuid4().hex[:12]}",
        "type": "restyle",
        "status": "queued",
        "created_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "elapsed_ms": None,
        "request": {
            "instruction": instruction,
            "part": req.part,
            "count": req.count,
            "size": req.size,
            "model": requested_model,
            "has_garment": bool(garment_path),
        },
        "image_url": f"/api/asset/{req.image_id}",
        "prompt": prompt,
        "model": requested_model,
        "cost": cost,
        "images": [],
        "error": None,
    }
    with _tasks_lock:
        _tasks[task["id"]] = task
        _save_task(task)

    _executor.submit(
        _run_task,
        task["id"],
        "restyle",
        {
            "image": str(image_path),
            "instructions": [instruction] if instruction else None,
            "garment": str(garment_path) if garment_path else None,
            "part": req.part,
            "count": req.count,
            "size": req.size,
            "model": req.model,
        },
    )
    return dict(task)


@app.post("/api/tryon")
def api_tryon(req: TryonRequest) -> dict:
    person_path = _asset_path(req.person_image_id)
    garment_path = _asset_path(req.garment_id)
    bottom_path = _asset_path(req.bottom_garment_id)

    if req.part not in VALID_PARTS:
        raise HTTPException(status_code=400, detail="部位参数不合法")
    if req.part == "full" and not bottom_path:
        raise HTTPException(status_code=400, detail="整套模式需要上传下装图")
    if not 1 <= req.variants <= 4:
        raise HTTPException(status_code=400, detail="生成数量需在 1~4 之间")
    if req.method not in {"auto", "seedream", "qwen"}:
        raise HTTPException(status_code=400, detail="生成方式不合法")

    part_label = PART_LABELS.get(req.part, "服装")
    desc = (req.desc or "").strip() or f"{part_label}服装"

    # 干跑：解析实际方法、组装 Prompt、校验参数
    try:
        plan, _ = run_tryon(
            settings=settings,
            garment=str(garment_path),
            model=str(person_path),
            desc=desc,
            bottom_garment=str(bottom_path) if bottom_path else None,
            part=req.part,
            variants=req.variants,
            method=req.method,
            size=req.size,
            dry_run=True,
        )
    except (ValueError, ProviderError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resolved_method = plan.method
    used_model = (
        settings.tryon_model if resolved_method == "qwen" else settings.ark_image_model
    )
    prices = load_prices()
    cost = {
        "unit": prices.get(used_model),
        "estimated": estimate_cost(used_model, req.variants, prices),
        "amount": None,
        "currency": CURRENCY,
    }

    if req.dry_run:
        return {
            "status": "dry_run",
            "prompt": plan.prompt,
            "model": used_model,
            "method": resolved_method,
            "engine": plan.details.get("engine"),
            "references": plan.references,
            "cost": cost,
        }

    if resolved_method == "qwen" and not settings.dashscope_api_key:
        raise HTTPException(status_code=503, detail="未配置 DASHSCOPE_API_KEY，无法使用百炼试衣")
    if resolved_method == "seedream" and not settings.ark_api_key:
        raise HTTPException(status_code=503, detail="未配置 ARK_API_KEY，无法使用 Seedream 试衣")

    task = {
        "id": f"task_{uuid.uuid4().hex[:12]}",
        "type": "tryon",
        "status": "queued",
        "created_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "elapsed_ms": None,
        "request": {
            "part": req.part,
            "method": resolved_method,
            "requested_method": req.method,
            "variants": req.variants,
            "size": req.size,
            "desc": desc,
            "has_bottom": bool(bottom_path),
        },
        "image_url": f"/api/asset/{req.person_image_id}",
        "prompt": plan.prompt,
        "model": used_model,
        "method": resolved_method,
        "cost": cost,
        "images": [],
        "error": None,
    }
    with _tasks_lock:
        _tasks[task["id"]] = task
        _save_task(task)

    _executor.submit(
        _run_task,
        task["id"],
        "tryon",
        {
            "garment": str(garment_path),
            "model": str(person_path),
            "desc": desc,
            "bottom_garment": str(bottom_path) if bottom_path else None,
            "part": req.part,
            "variants": req.variants,
            "method": req.method,
            "size": req.size,
        },
    )
    return dict(task)


@app.post("/api/video")
def api_video(req: VideoRequest) -> dict:
    image_path = _asset_path(req.image_id)
    if req.duration not in {5, 10}:
        raise HTTPException(status_code=400, detail="视频时长仅支持 5 秒或 10 秒")
    if req.resolution not in {"480P", "720P", "1080P"}:
        raise HTTPException(status_code=400, detail="分辨率需为 480P / 720P / 1080P")
    if req.method not in {"auto", "wan", "seedance"}:
        raise HTTPException(status_code=400, detail="生成方式不合法")

    prompt = (req.prompt or "").strip() or None
    try:
        plan, _ = run_video(
            settings=settings,
            image=str(image_path),
            prompt=prompt,
            duration=req.duration,
            resolution=req.resolution,
            method=req.method,
            dry_run=True,
        )
    except (ValueError, ProviderError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    used_model = plan.details.get("model") or ""
    video_prices = load_video_prices()
    cost = {
        "unit": video_prices.get(req.resolution),
        "estimated": estimate_video_cost(req.resolution, req.duration, video_prices),
        "amount": None,
        "currency": CURRENCY,
        "unit_type": "second",
        "duration": req.duration,
        "resolution": req.resolution,
    }

    if req.dry_run:
        return {
            "status": "dry_run",
            "prompt": plan.prompt,
            "model": used_model,
            "method": plan.method,
            "cost": cost,
        }

    if plan.method == "wan-i2v" and not settings.dashscope_api_key:
        raise HTTPException(status_code=503, detail="未配置 DASHSCOPE_API_KEY，无法生成视频")
    if plan.method == "seedance" and not settings.ark_api_key:
        raise HTTPException(status_code=503, detail="未配置 ARK_API_KEY，无法生成视频")

    task = {
        "id": f"task_{uuid.uuid4().hex[:12]}",
        "type": "video",
        "status": "queued",
        "created_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "elapsed_ms": None,
        "request": {
            "prompt": prompt or "",
            "duration": req.duration,
            "resolution": req.resolution,
            "method": plan.method,
            "requested_method": req.method,
        },
        "image_url": f"/api/asset/{req.image_id}",
        "prompt": plan.prompt,
        "model": used_model,
        "method": plan.method,
        "cost": cost,
        "images": [],
        "video": None,
        "error": None,
    }
    with _tasks_lock:
        _tasks[task["id"]] = task
        _save_task(task)

    _executor.submit(
        _run_task,
        task["id"],
        "video",
        {
            "image": str(image_path),
            "prompt": prompt,
            "duration": req.duration,
            "resolution": req.resolution,
            "method": req.method,
        },
    )
    return dict(task)


def _run_task(task_id: str, kind: str, params: dict) -> None:
    started = time.time()
    _update_task(task_id, status="running", started_at=started)
    default_models = {
        "restyle": settings.qwen_image_edit_model,
        "tryon": settings.tryon_model,
        "video": settings.video_model,
    }
    used_model = default_models.get(kind, "")
    images: list[dict] = []
    video: dict | None = None
    outcome = "failed"
    error: str | None = None
    prompt: str | None = None
    fallback: str | None = None
    try:
        if kind == "restyle":
            plans, records = run_restyle(
                settings=settings, fresh_session=True, **params
            )
            plan = plans[0]
            used_model = (
                plan.details.get("used_model")
                or plan.details.get("model")
                or settings.qwen_image_edit_model
            )
            prompt = plan.prompt
        elif kind == "tryon":
            plan, records = run_tryon(
                settings=settings, fresh_session=True, **params
            )
            used_model = plan.details.get("used_model") or (
                settings.tryon_model
                if plan.method == "qwen"
                else settings.ark_image_model
            )
            prompt = plan.prompt
            fallback = plan.details.get("fallback")
        elif kind == "video":
            plan, records = run_video(
                settings=settings, fresh_session=True, **params
            )
            used_model = plan.details.get("model") or settings.video_model
            prompt = plan.prompt
            if records:
                video = {
                    "url": _file_url(records[0]["path"]),
                    "name": Path(records[0]["path"]).name,
                }
        else:
            raise ValueError(f"未知任务类型：{kind}")

        if kind != "video":
            images = [
                {"url": _file_url(record["path"]), "name": Path(record["path"]).name}
                for record in records
            ]
            # 提前生成缩略图，历史页打开即可见
            for image in images:
                _ensure_thumb(image.get("url", ""))
        outcome = "succeeded"
    except Exception as exc:  # 任务失败要落盘，前端可读
        error = f"{type(exc).__name__}: {exc}"
    finally:
        elapsed = int((time.time() - started) * 1000)
        if kind == "video":
            video_prices = load_video_prices()
            resolution = str(params.get("resolution") or "480P")
            duration = int(params.get("duration") or 5)
            unit_price = video_prices.get(resolution) if outcome == "succeeded" else None
            amount = round(unit_price * duration, 4) if unit_price is not None else None
            cost_fields = {
                "unit": unit_price,
                "amount": amount,
                "currency": CURRENCY,
                "unit_type": "second",
                "duration": duration,
                "resolution": resolution,
            }
        else:
            prices = load_prices()
            unit_price = prices.get(used_model) if outcome == "succeeded" else None
            amount = round(unit_price * len(images), 4) if unit_price is not None else None
            cost_fields = {
                "unit": unit_price,
                "amount": amount,
                "currency": CURRENCY,
            }
        # 一次写入终态，避免 SSE 读到「成功但还没有耗时/费用」的中间态
        fields: dict = {
            "status": outcome,
            "finished_at": time.time(),
            "elapsed_ms": elapsed,
            "used_model": used_model,
            "cost": cost_fields,
        }
        if video:
            fields["video"] = video
        if images:
            fields["images"] = images
        if prompt:
            fields["prompt"] = prompt
        if fallback:
            fields["fallback"] = fallback
        if error:
            fields["error"] = error
        _update_task(task_id, **fields)
        note = ""
        if kind == "restyle":
            note = " / ".join(item for item in (params.get("instructions") or []) if item)
        elif kind == "tryon":
            note = f"part={params.get('part')} method={params.get('method')}"
        elif kind == "video":
            note = f"{params.get('resolution')} {params.get('duration')}s method={params.get('method')}"
        ledger.record(
            task_id=task_id,
            action=kind,
            status=outcome,
            model=used_model,
            images=len(images) if outcome == "succeeded" else 0,
            unit_price=unit_price,
            amount=amount or 0.0,
            elapsed_ms=elapsed,
            instruction=note,
        )


@app.get("/api/tasks/{task_id}")
def api_task(task_id: str) -> dict:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return dict(task)


@app.get("/api/tasks/{task_id}/events")
async def api_task_events(task_id: str) -> StreamingResponse:
    """SSE 推送任务状态；终态后自动结束。"""

    async def event_stream():
        last_payload: str | None = None
        idle = 0
        while True:
            with _tasks_lock:
                task = _tasks.get(task_id)
                snapshot = dict(task) if task else None
            if snapshot is None:
                yield 'event: error\ndata: {"detail":"任务不存在"}\n\n'
                return
            payload = json.dumps(snapshot, ensure_ascii=False)
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            if snapshot.get("status") in ("succeeded", "failed"):
                return
            idle += 1
            if idle % 15 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/tasks")
def api_tasks() -> list[dict]:
    with _tasks_lock:
        tasks = sorted(_tasks.values(), key=lambda t: t.get("created_at", 0), reverse=True)
        return [
            {
                "id": task["id"],
                "type": task.get("type"),
                "status": task["status"],
                "created_at": task.get("created_at"),
                "elapsed_ms": task.get("elapsed_ms"),
                "model": task.get("used_model") or task.get("model"),
                "instruction": (task.get("request") or {}).get("instruction"),
                "cost": task.get("cost"),
            }
            for task in tasks[:20]
        ]


@app.get("/api/costs")
def api_costs() -> dict:
    return ledger.summary()


@app.post("/api/balance/config")
def api_balance_config(req: BalanceConfigRequest) -> dict:
    """保存阿里云 AccessKey 到本机 .env（不回显 Secret）。"""
    key_id = req.access_key_id.strip()
    secret = req.access_key_secret.strip()
    if not key_id or not secret:
        raise HTTPException(status_code=400, detail="请填写 AccessKey ID 和 AccessKey Secret")
    if len(secret) < 16:
        raise HTTPException(status_code=400, detail="AccessKey Secret 长度异常，请检查是否复制完整")
    warning = ""
    if not key_id.startswith("LTAI"):
        warning = "AccessKey ID 通常以 LTAI 开头；sk- 开头的百炼 Key 不能查询余额。"
    _save_balance_credentials(key_id, secret)
    return {
        "saved": True,
        "access_key_id_masked": _mask_key(key_id),
        "warning": warning,
        "env_path": str(ENV_PATH),
    }


@app.delete("/api/balance/config")
def api_balance_clear() -> dict:
    """清除本机保存的 AccessKey。"""
    _save_balance_credentials("", "")
    return {"cleared": True}


@app.get("/api/balance")
def api_balance() -> dict:
    """账户余额 + 本地成本 + 最近额度错误。"""
    result = query_account_balance(settings)
    result["access_key_id_masked"] = _mask_key(settings.aliyun_access_key_id)
    summary = ledger.summary()
    result["cost_summary"] = {
        "total_amount": summary["total_amount"],
        "calls": summary["calls"],
        "currency": summary["currency"],
    }
    result["dashscope_key_configured"] = bool(settings.dashscope_api_key)
    result["stylist_model"] = settings.stylist_model
    result["video_model"] = settings.video_model
    result["console_url"] = "https://bailian.console.aliyun.com/"

    markers = ("AllocationQuota", "Arrearage", "InsufficientBalance", "FreeTierOnly")
    with _tasks_lock:
        candidates = [
            task
            for task in _tasks.values()
            if any(marker in str(task.get("error") or "") for marker in markers)
        ]
    if candidates:
        latest = max(candidates, key=lambda task: task.get("created_at") or 0)
        result["recent_quota_error"] = {
            "task_id": latest.get("id"),
            "type": latest.get("type"),
            "created_at": latest.get("created_at"),
            "error": (latest.get("error") or "")[:300],
        }
    else:
        result["recent_quota_error"] = None
    return result


@app.get("/api/models")
def api_models() -> list[dict]:
    """内置模特库：45 个模特及图片地址（不暴露本地绝对路径）。"""
    models = load_models(settings.model_lib)
    result = []
    for model in models:
        model_id = str(model.get("id") or "")
        image = get_model_image(model, settings.assets_dir)
        if not image:
            image_url = ""
        elif image.startswith(("http://", "https://")):
            image_url = image
        else:
            image_url = f"/api/models/{model_id}/image"
        result.append(
            {
                "id": model_id,
                "name": model.get("name", ""),
                "style": model.get("style", ""),
                "gender": model.get("gender", ""),
                "ageGroup": model.get("ageGroup", ""),
                "height": model.get("height", ""),
                "weight": model.get("weight", ""),
                "bodyType": model.get("bodyType", ""),
                "desc": model.get("desc", ""),
                "default": bool(model.get("default")),
                "image_url": image_url,
            }
        )
    return result


@app.get("/api/models/{model_id}/image")
def api_model_image(model_id: str):
    model = next(
        (item for item in load_models(settings.model_lib) if str(item.get("id")) == model_id),
        None,
    )
    if not model:
        raise HTTPException(status_code=404, detail="模特不存在")
    image = get_model_image(model, settings.assets_dir)
    if not image:
        raise HTTPException(status_code=404, detail="模特图片不存在")
    if image.startswith(("http://", "https://")):
        return RedirectResponse(image)
    path = Path(image)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="模特图片不存在")
    return FileResponse(path, media_type=MEDIA_TYPES.get(path.suffix.lower(), "image/png"))


@app.post("/api/stylist")
def api_stylist(req: StylistRequest) -> dict:
    """智能穿搭：LLM 从内置衣橱选品，返回 3 套方案。"""
    if req.occasion not in OCCASIONS:
        raise HTTPException(status_code=400, detail=f"场合需为：{'/'.join(OCCASIONS)}")
    if req.season not in SEASONS:
        raise HTTPException(status_code=400, detail=f"季节需为：{'/'.join(SEASONS)}")
    if req.palette not in PALETTES:
        raise HTTPException(status_code=400, detail=f"色系需为：{'/'.join(PALETTES)}")
    result = generate_schemes(
        settings,
        occasion=req.occasion,
        season=req.season,
        palette=req.palette,
        anchor=(req.anchor or "").strip(),
    )
    result["options"] = {
        "occasions": OCCASIONS,
        "seasons": SEASONS,
        "palettes": PALETTES,
    }
    return result


@app.get("/api/lookbook/{task_id}")
def api_lookbook(task_id: str) -> FileResponse:
    """把一条生成记录打包成 Lookbook ZIP（主图 3:4 + 详情图 1:1 + 文案 + 参数 + 成本）。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        snapshot = dict(task)
        snapshot["images"] = [dict(image) for image in (task.get("images") or [])]
    if not snapshot["images"]:
        raise HTTPException(status_code=404, detail="该记录没有可导出的图片")
    zip_path = build_lookbook(settings, snapshot)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"lookbook_{task_id}.zip",
    )


@app.get("/api/history")
def api_history(limit: int = 50) -> list[dict]:
    """生成历史：只返回仍有图片的任务，按时间倒序。"""
    limit = max(1, min(limit, 200))
    with _tasks_lock:
        tasks = [
            task
            for task in _tasks.values()
            if task.get("images") or task.get("video")
        ]
    tasks.sort(key=lambda task: task.get("created_at", 0), reverse=True)
    return [_history_item(task) for task in tasks[:limit]]


@app.delete("/api/history/{task_id}/images/{index}")
def api_delete_history_image(task_id: str, index: int) -> dict:
    """删除单张生成图片；任务其余图片保留。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task.get("status") in ("queued", "running"):
            raise HTTPException(status_code=409, detail="任务进行中，暂不能删除")
        images = list(task.get("images") or [])
        if index < 0 or index >= len(images):
            raise HTTPException(status_code=404, detail="图片不存在")
        image = images[index]

    deleted_file = _delete_file_for_url(image.get("url", ""))
    images.pop(index)
    removed_task = False
    if images:
        _update_task(task_id, images=images)
    else:
        # 最后一张删完后，整条记录也不再出现在历史里
        with _tasks_lock:
            _tasks.pop(task_id, None)
            (TASK_DIR / f"{task_id}.json").unlink(missing_ok=True)
        task_store.delete(task_id)
        removed_task = True
    return {
        "task_id": task_id,
        "deleted_file": deleted_file,
        "remaining": len(images),
        "removed_task": removed_task,
        "images": images,
    }


@app.delete("/api/history/{task_id}")
def api_delete_history(task_id: str) -> dict:
    """删除一条历史记录及其所有生成图片。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task.get("status") in ("queued", "running"):
            raise HTTPException(status_code=409, detail="任务进行中，暂不能删除")
        images = list(task.get("images") or [])
        video = task.get("video") or {}

    deleted_images = sum(1 for image in images if _delete_file_for_url(image.get("url", "")))
    deleted_video = _delete_file_for_url(video.get("url", ""))
    with _tasks_lock:
        _tasks.pop(task_id, None)
        (TASK_DIR / f"{task_id}.json").unlink(missing_ok=True)
    task_store.delete(task_id)
    return {
        "task_id": task_id,
        "deleted_images": deleted_images,
        "deleted_video": deleted_video,
    }


@app.get("/thumb/{relpath:path}")
def api_thumb(relpath: str, w: int = 480) -> FileResponse:
    """按需生成并缓存缩略图，避免历史页一次性拉取多张原图。"""
    base = settings.output_dir.resolve()
    src = (base / relpath).resolve()
    if src == base or base not in src.parents:
        raise HTTPException(status_code=403, detail="非法路径")
    if not src.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    cache = _ensure_thumb("/files/" + relpath, width=w)
    if cache:
        return FileResponse(cache, media_type="image/jpeg")
    return FileResponse(src)


@app.get("/files/{relpath:path}")
def api_file(relpath: str) -> FileResponse:
    base = settings.output_dir.resolve()
    path = (base / relpath).resolve()
    if path != base and base not in path.parents:
        raise HTTPException(status_code=403, detail="非法路径")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path)


if __name__ == "__main__":
    import uvicorn

    # 直接传 app 对象，避免 "app:app" 在 __main__ 场景下二次导入、生成两套任务表
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
