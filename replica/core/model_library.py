"""内置数字模特库：读取 models.json、展示、推荐、取图。"""
from __future__ import annotations

import json
from pathlib import Path


def load_models(model_lib: Path) -> list[dict]:
    if not model_lib.exists():
        raise FileNotFoundError(f"模特库不存在：{model_lib}")
    with model_lib.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("models.json 必须是数组")
    return data


def get_model_image(model: dict, assets_root: Path) -> str | None:
    """返回本地图片绝对路径；不存在则返回 models.json 里的 url（如果有）。"""
    local = model.get("local")
    if local:
        path = (assets_root.parent / local).resolve()
        # assets_root = <root>/assets，models.json 里的 local 形如 assets/models/02.png
        if path.exists():
            return str(path)
        alt = (assets_root / local).resolve()
        if alt.exists():
            return str(alt)
    return model.get("url")


def list_models(models: list[dict], gender: str | None = None, age_group: str | None = None) -> list[dict]:
    result = models
    if gender:
        result = [m for m in result if m.get("gender") == gender]
    if age_group:
        result = [m for m in result if m.get("ageGroup") == age_group]
    return result


def recommend_model(
    models: list[dict],
    garment_desc: str = "",
    gender: str | None = None,
    style: str | None = None,
    age_group: str = "adult",
) -> dict:
    """根据服装描述/性别/风格推荐模特，规则与参考项目一致。"""
    desc_lower = garment_desc.lower()

    if gender is None:
        child_keywords = ["童装", "儿童", "小孩", "宝宝", "child", "kid"]
        male_keywords = ["男", "boy", "male", "先生", "男装", "男款"]
        if any(k in desc_lower for k in child_keywords):
            age_group = "child"
        gender = "male" if any(k in desc_lower for k in male_keywords) else "female"

    candidates = [m for m in models if m.get("ageGroup") == age_group]
    gender_matched = [m for m in candidates if m.get("gender") == gender]
    if gender_matched:
        candidates = gender_matched
    if not candidates:
        candidates = models

    if style:
        style_matched = [m for m in candidates if style in m.get("style", "")]
        if style_matched:
            return style_matched[0]

    if garment_desc:
        desc_matched = [
            m
            for m in candidates
            if any(
                kw and kw in desc_lower
                for kw in str(m.get("desc", "")).replace("，", "、").split("、")
            )
        ]
        if desc_matched:
            return desc_matched[0]

    return next((m for m in candidates if m.get("default")), candidates[0])


def format_model_list(models: list[dict]) -> str:
    groups = [
        ("女装模特", [m for m in models if m.get("gender") == "female" and m.get("ageGroup") == "adult"]),
        ("男装模特", [m for m in models if m.get("gender") == "male" and m.get("ageGroup") == "adult"]),
        ("童装模特", [m for m in models if m.get("ageGroup") == "child"]),
    ]
    lines: list[str] = []
    for title, items in groups:
        if not items:
            continue
        lines.append(f"{title}（{len(items)}）")
        for model in items:
            lines.append(
                f"  - {model.get('id', '?')} {model.get('name', '')} | {model.get('style', '')} | "
                f"{model.get('height', '')} | {model.get('bodyType', '')}"
            )
            if model.get("desc"):
                lines.append(f"      {model['desc']}")
        lines.append("")
    return "\n".join(lines).rstrip()
