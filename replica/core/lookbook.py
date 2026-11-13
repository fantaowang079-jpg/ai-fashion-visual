"""Lookbook 一键导出：图片 + 搭配文案 + 生成参数 + 成本清单 -> ZIP。"""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from config import Settings

PART_LABELS = {
    "top": "上装",
    "bottom": "下装",
    "one_piece": "连衣裙/连体装",
    "full": "整套上下装",
}

TYPE_LABELS = {"tryon": "虚拟试衣", "restyle": "AI 换装"}


def _resolve_image(settings: Settings, url: str) -> Path | None:
    if not url or not url.startswith("/files/"):
        return None
    rel = unquote(url[len("/files/") :])
    base = settings.output_dir.resolve()
    path = (base / rel).resolve()
    if base not in path.parents or not path.is_file():
        return None
    return path


def _save_ratio(image, path: Path, ratio: tuple[int, int], max_width: int) -> None:
    width, height = image.size
    target = ratio[0] / ratio[1]
    if width / height > target:
        new_width = int(height * target)
        left = (width - new_width) // 2
        box = (left, 0, left + new_width, height)
    else:
        new_height = int(width / target)
        top = (height - new_height) // 2
        box = (0, top, width, top + new_height)
    cropped = image.crop(box)
    if cropped.width > max_width:
        from PIL import Image

        cropped = cropped.resize(
            (max_width, int(max_width * ratio[1] / ratio[0])),
            Image.Resampling.LANCZOS,
        )
    cropped.save(path, "JPEG", quality=92, optimize=True)


def _save_variants(source: Path, images_dir: Path, index: int) -> None:
    """输出原图 + 主图 3:4 + 详情图 1:1；Pillow 不可用时仅复制原图。"""
    try:
        from PIL import Image

        with Image.open(source) as image:
            rgb = image.convert("RGB")
            _save_ratio(rgb, images_dir / f"{index:02d}_main_3x4.jpg", (3, 4), 1200)
            _save_ratio(rgb, images_dir / f"{index:02d}_detail_1x1.jpg", (1, 1), 900)
    except Exception:
        pass
    shutil.copy2(source, images_dir / f"{index:02d}_original{source.suffix}")


def _task_title(task: dict) -> str:
    request = task.get("request") or {}
    if task.get("type") == "tryon":
        return request.get("desc") or f"{PART_LABELS.get(request.get('part'), '服装')}试衣"
    return request.get("instruction") or (
        "按服装图换装" if request.get("has_garment") else "AI 换装"
    )


def _copy_text(task: dict, title: str) -> str:
    request = task.get("request") or {}
    if task.get("type") == "tryon":
        desc = request.get("desc") or title
        return (
            f"以「{desc}」为核心单品，保留人物自然姿态与干净背景，"
            "呈现适合通勤与日常出街的完整造型。整体配色克制，强调面料质感与版型轮廓。"
        )
    instruction = request.get("instruction") or title
    return (
        f"围绕「{instruction}」展开搭配，保持人物面部、发型与姿势不变，"
        "用干净的背景突出服装主体。整体风格简洁利落，适合电商主图与详情页展示。"
    )


def _format_time(task: dict) -> str:
    created = task.get("created_at")
    if not created:
        return "—"
    return datetime.fromtimestamp(float(created)).strftime("%Y-%m-%d %H:%M")


def _markdown(task: dict, title: str, image_count: int) -> str:
    request = task.get("request") or {}
    cost = task.get("cost") or {}
    amount = cost.get("amount")
    unit = cost.get("unit")
    elapsed = task.get("elapsed_ms")
    prompt = task.get("prompt") or ""
    model = task.get("used_model") or task.get("model") or "—"
    kind = TYPE_LABELS.get(task.get("type"), "AI 换装")

    lines = [
        f"# {title}",
        "",
        "> 由衣镜 Studio 生成的 AI Lookbook；发布时请按平台规范标注 AI 生成内容。",
        "",
        "## 基本信息",
        f"- 类型：{kind}",
        f"- 生成时间：{_format_time(task)}",
        f"- 使用模型：{model}",
        f"- 图片数量：{image_count}",
        f"- 生成耗时：{elapsed / 1000:.1f} 秒" if elapsed else "- 生成耗时：—",
        (
            f"- 估算费用：¥{float(amount):.2f}（估算，以控制台账单为准）"
            if amount is not None
            else "- 估算费用：—"
        ),
        "",
        "## 搭配文案",
        _copy_text(task, title),
        "",
        "## 场景建议",
        "- 棚拍主图：白底/浅灰底，突出服装轮廓与版型",
        "- 街拍场景：自然光与城市背景，适合内容种草",
        "- 通勤场景：办公室或咖啡店，呈现日常穿着",
        "- 细节特写：领口、袖口、面料纹理与配饰",
        "",
        "## 生成参数",
        f"- 部位：{PART_LABELS.get(request.get('part'), request.get('part') or '—')}",
        f"- 指令/描述：{request.get('instruction') or request.get('desc') or title}",
        f"- 生成方式：{request.get('method') or request.get('model') or model}",
        "",
        "### 提示词",
        "```",
        prompt,
        "```",
        "",
        "## 图片清单",
    ]
    for index in range(1, image_count + 1):
        lines.extend(
            [
                f"- `images/{index:02d}_main_3x4.jpg`：主图 3:4",
                f"- `images/{index:02d}_detail_1x1.jpg`：详情图 1:1",
                f"- `images/{index:02d}_original.*`：原图",
            ]
        )
    if image_count == 0:
        lines.append("- 无可用图片")
    lines.extend(
        [
            "",
            "## 成本清单",
            f"- 单价：{'¥%.2f/张' % float(unit) if unit is not None else '待核对'}",
            f"- 数量：{image_count}",
            f"- 合计：{'¥%.2f' % float(amount) if amount is not None else '待核对'}（估算）",
            "",
            "## 免责声明",
            "本 Lookbook 由 AI 生成，服装细节可能与实物存在差异；费用为估算值，以控制台账单为准。",
            "",
        ]
    )
    return "\n".join(lines)


def build_lookbook(settings: Settings, task: dict) -> Path:
    """打包一个任务的图片、文案与元数据，返回 ZIP 路径。"""
    task_id = str(task.get("id") or "task")
    title = _task_title(task)
    images = task.get("images") or []

    output_dir = settings.output_dir.resolve()
    lookbook_dir = output_dir / "lookbooks"
    lookbook_dir.mkdir(parents=True, exist_ok=True)
    zip_path = lookbook_dir / f"lookbook_{task_id}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / f"lookbook_{task_id}"
        images_dir = root / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        used = 0
        for index, image in enumerate(images, 1):
            source = _resolve_image(settings, image.get("url", ""))
            if not source:
                continue
            _save_variants(source, images_dir, index)
            used += 1

        manifest = {
            "task_id": task_id,
            "title": title,
            "type": task.get("type"),
            "created_at": task.get("created_at"),
            "model": task.get("used_model") or task.get("model"),
            "elapsed_ms": task.get("elapsed_ms"),
            "cost": task.get("cost"),
            "request": task.get("request"),
            "prompt": task.get("prompt"),
            "image_count": used,
            "images": task.get("images"),
        }
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (root / "lookbook.md").write_text(
            _markdown(task, title, used), encoding="utf-8"
        )

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root.parent))

    return zip_path
