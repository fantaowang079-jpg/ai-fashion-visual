"""成本台账：按模型估算单价、记录每次生成、提供汇总。

单价为估算值，可通过 `.env` 的 `QWEN_IMAGE_EDIT_PRICES` 覆盖，实际以控制台账单为准。
格式：`模型=单价,模型=单价`，单位元/张。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import ROOT  # noqa: F401  确保 .env 已加载

DEFAULT_PRICES: dict[str, float] = {
    # 换装（百炼 qwen-image 系列）
    "qwen-image-3.0": 0.50,
    "qwen-image-2.1-pro": 0.30,
    "qwen-image-2.0": 0.20,
    # 试衣
    "aitryon-plus": 0.50,
    # 方舟 Seedream（价格待按控制台核对）
    "doubao-seedream-5-0-260128": 0.25,
}

CURRENCY = "CNY"

# 万相图生视频：按秒计费（元/秒）
DEFAULT_VIDEO_PRICES: dict[str, float] = {
    "480P": 0.30,
    "720P": 0.60,
    "1080P": 1.00,
}


def load_video_prices() -> dict[str, float]:
    """默认视频单价 + `.env` 的 WAN_VIDEO_PRICES 覆盖。"""
    prices = dict(DEFAULT_VIDEO_PRICES)
    raw = os.getenv("WAN_VIDEO_PRICES", "").strip()
    for item in raw.split(","):
        if "=" not in item:
            continue
        resolution, _, value = item.partition("=")
        try:
            prices[resolution.strip()] = float(value.strip())
        except ValueError:
            continue
    return prices


def estimate_video_cost(
    resolution: str | None,
    duration: int,
    prices: dict[str, float] | None = None,
) -> float | None:
    """估算视频费用：单价（元/秒）× 时长。"""
    if not resolution or duration < 1:
        return None
    unit = (prices or load_video_prices()).get(resolution)
    if unit is None:
        return None
    return round(unit * int(duration), 4)


def load_prices() -> dict[str, float]:
    """默认估算价 + `.env` 覆盖。"""
    prices = dict(DEFAULT_PRICES)
    raw = os.getenv("QWEN_IMAGE_EDIT_PRICES", "").strip()
    for item in raw.split(","):
        if "=" not in item:
            continue
        model, _, value = item.partition("=")
        try:
            prices[model.strip()] = float(value.strip())
        except ValueError:
            continue
    return prices


def estimate_cost(model: str | None, count: int, prices: dict[str, float] | None = None) -> float | None:
    """估算一次生成的费用（元）；模型无价格时返回 None。"""
    if not model or count < 1:
        return None
    price = (prices or load_prices()).get(model)
    if price is None:
        return None
    return round(price * count, 4)


class CostLedger:
    """追加写入 JSONL 的成本台账，线程安全。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(self, **fields) -> dict:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **fields,
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def entries(self, limit: int = 200) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        items: list[dict] = []
        for line in lines:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(items))

    def summary(self, recent_limit: int = 50) -> dict:
        entries = self.entries(limit=10000)
        total_amount = 0.0
        total_images = 0
        by_model: dict[str, dict] = {}
        for entry in entries:
            amount = float(entry.get("amount") or 0)
            images = int(entry.get("images") or 0)
            total_amount += amount
            total_images += images
            model = str(entry.get("model") or "unknown")
            slot = by_model.setdefault(model, {"calls": 0, "images": 0, "amount": 0.0})
            slot["calls"] += 1
            slot["images"] += images
            slot["amount"] = round(slot["amount"] + amount, 4)

        return {
            "currency": CURRENCY,
            "total_amount": round(total_amount, 4),
            "total_images": total_images,
            "calls": len(entries),
            "by_model": by_model,
            "recent": entries[:recent_limit],
        }
