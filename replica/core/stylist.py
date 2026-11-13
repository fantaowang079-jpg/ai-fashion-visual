"""智能穿搭：LLM 从内置衣橱选品，输出 3 套结构化搭配方案。

约束：只允许选择 `assets/wardrobe.json` 中的单品，避免编造不存在的 SKU。
LLM 不可用时回退到规则模板，保证演示不中断。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from config import ROOT, Settings

WARDROBE_PATH = ROOT / "assets" / "wardrobe.json"

OCCASIONS = ["通勤", "约会", "旅行", "运动", "正式"]
SEASONS = ["春夏", "秋冬", "春秋", "四季"]
PALETTES = ["中性", "黑白", "暖色", "冷色", "莫兰迪"]


def load_wardrobe(path: Path | None = None) -> list[dict]:
    path = Path(path) if path else WARDROBE_PATH
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("wardrobe.json 必须是数组")
    return data


def _public_item(item: dict) -> dict:
    return {
        "id": item["id"],
        "name": item["name"],
        "category": item.get("category", ""),
        "color": item.get("color", ""),
        "style": item.get("style", ""),
    }


def _instruction(title: str, items: list[dict]) -> str:
    names = "、".join(item["name"] for item in items)
    return f"按「{title}」搭配，穿{names}，保持自然姿态与干净背景，整体风格统一"


def _make_scheme(
    title: str,
    item_ids: list[str],
    wardrobe: list[dict],
    reason: str,
    tips: list[str],
    anchor: str = "",
) -> dict:
    by_id = {item["id"]: item for item in wardrobe}
    items = [_public_item(by_id[item_id]) for item_id in item_ids if item_id in by_id]
    colors: list[str] = []
    for item in items:
        if item["color"] and item["color"] not in colors:
            colors.append(item["color"])
    return {
        "id": "",
        "title": title,
        "item_ids": [item["id"] for item in items],
        "items": items,
        "colors": colors,
        "reason": reason,
        "tips": tips,
        "anchor": anchor,
        "instruction": _instruction(title, items),
    }


def fallback_schemes(
    occasion: str = "通勤",
    season: str = "四季",
    palette: str = "中性",
    anchor: str = "",
) -> dict:
    """LLM 不可用时的规则模板，保证返回 3 套合法方案。"""
    wardrobe = load_wardrobe()
    templates = [
        (
            "通勤简约",
            ["W01", "W07", "W15", "W16"],
            "白衬衫配黑色西装裤，利落干净，适合日常通勤。",
            ["衬衫下摆塞进裤腰，比例更利落", "托特包与乐福鞋保持同色系"],
        ),
        (
            "轻松休闲",
            ["W02", "W08", "W14", "W19"],
            "针织开衫配牛仔裤，松弛但不邋遢，适合周末出行。",
            ["开衫只扣中间一颗扣子，更显随性", "棒球帽增加旅行感"],
        ),
        (
            "约会精致",
            ["W12", "W15", "W17", "W18"],
            "黑色缎面连衣裙，用金属配饰提亮，适合晚间约会。",
            ["项链与链条包金属色保持一致", "鞋包同色更显高级"],
        ),
    ]
    schemes = []
    for index, (title, item_ids, reason, tips) in enumerate(templates, 1):
        scheme = _make_scheme(
            title,
            item_ids,
            wardrobe,
            f"{reason} 场合：{occasion}；季节：{season}；色系偏好：{palette}。",
            tips,
            anchor,
        )
        scheme["id"] = f"look_{index}"
        schemes.append(scheme)
    return {"schemes": schemes}


def build_prompt(
    wardrobe: list[dict],
    occasion: str,
    season: str,
    palette: str,
    anchor: str,
) -> str:
    lines = "\n".join(
        f"{item['id']} | {item['name']} | {item.get('category', '')} | "
        f"{item.get('color', '')} | {item.get('style', '')}"
        for item in wardrobe
    )
    return f"""你是资深电商服装搭配师。只能从下面衣橱中选择单品，禁止编造清单外的单品或 ID。
衣橱（ID | 名称 | 类别 | 颜色 | 风格）：
{lines}

用户偏好：
- 场合：{occasion}
- 季节：{season}
- 色系：{palette}
- 起点单品：{anchor or "无"}

请输出 3 套可直接上身的搭配方案，每套 3-5 件，必须包含上装/下装（或连衣裙）与鞋；
优先符合场合和季节，色系协调，三套之间不要重复使用同一件核心单品。
只输出 JSON，不要代码块和解释：
{{"schemes":[{{"title":"方案名","item_ids":["W01","W07"],"colors":["白色","黑色"],"reason":"适合该场合的原因","tips":["搭配要点1","搭配要点2"]}}]}}
"""


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if "```" in text:
        text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("模型返回的不是 JSON 对象")
    return data


def _normalize(
    raw: dict,
    wardrobe: list[dict],
    anchor: str,
    occasion: str,
    season: str,
    palette: str,
) -> list[dict]:
    by_id = {item["id"]: item for item in wardrobe}
    schemes: list[dict] = []
    for index, item in enumerate((raw.get("schemes") or [])[:3], 1):
        if not isinstance(item, dict):
            continue
        item_ids = [str(i) for i in (item.get("item_ids") or []) if str(i) in by_id]
        if not item_ids:
            continue
        title = str(item.get("title") or f"方案 {index}").strip()[:40]
        tips = [str(t).strip() for t in (item.get("tips") or []) if str(t).strip()][:4]
        reason = str(item.get("reason") or "").strip()
        if palette and palette not in reason:
            reason = f"{reason} 色系偏好：{palette}。".strip()
        scheme = _make_scheme(title, item_ids, wardrobe, reason, tips, anchor)
        scheme["id"] = f"look_{len(schemes) + 1}"
        schemes.append(scheme)

    if len(schemes) < 3:
        used_titles = {scheme["title"] for scheme in schemes}
        for extra in fallback_schemes(occasion, season, palette, anchor)["schemes"]:
            if len(schemes) >= 3:
                break
            if extra["title"] in used_titles:
                continue
            extra["id"] = f"look_{len(schemes) + 1}"
            used_titles.add(extra["title"])
            schemes.append(extra)

    for index, scheme in enumerate(schemes, 1):
        scheme["id"] = f"look_{index}"
    return schemes[:3]


def generate_schemes(
    settings: Settings,
    occasion: str = "通勤",
    season: str = "四季",
    palette: str = "中性",
    anchor: str = "",
) -> dict:
    """调用 LLM 生成 3 套方案；失败时返回规则模板。"""
    anchor = (anchor or "").strip()
    wardrobe = load_wardrobe()

    if not settings.dashscope_api_key:
        return {
            "schemes": fallback_schemes(occasion, season, palette, anchor)["schemes"],
            "model": "rule-based",
            "generated_by": "fallback",
            "note": "未配置 DASHSCOPE_API_KEY，已使用规则模板",
        }

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
        )
        completion = client.chat.completions.create(
            model=settings.stylist_model,
            messages=[
                {
                    "role": "user",
                    "content": build_prompt(wardrobe, occasion, season, palette, anchor),
                }
            ],
            temperature=0.7,
        )
        raw = (completion.choices[0].message.content or "").strip()
        schemes = _normalize(_parse_json(raw), wardrobe, anchor, occasion, season, palette)
        if not schemes:
            raise ValueError("模型没有给出有效方案")
        usage = getattr(completion, "usage", None)
        return {
            "schemes": schemes,
            "model": settings.stylist_model,
            "generated_by": "llm",
            "usage": usage.model_dump() if usage else None,
        }
    except Exception as exc:
        return {
            "schemes": fallback_schemes(occasion, season, palette, anchor)["schemes"],
            "model": "rule-based",
            "generated_by": "fallback",
            "note": f"LLM 调用失败，已使用规则模板：{exc}",
        }
