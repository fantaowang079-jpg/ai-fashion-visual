"""编排层：试穿、AI 换装、多角度、视频。

- 试穿：Seedream 多参考图 / 百炼 AI 试衣
- 换装：百炼 qwen-image 指令编辑（保留人物与背景，只改服装）
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from config import Settings
from providers import ArkProvider, DashScopeProvider, GeneratedImage, ProviderError
from core.model_library import get_model_image, load_models, recommend_model
from core.prompts import (
    ANGLE_PRESETS,
    MODEL_PROMPTS,
    build_angle_prompt,
    build_restyle_prompt,
    build_tryon_edit_prompt,
    build_tryon_prompt,
    build_video_prompt,
    build_wan_video_prompt,
)
from core.session import Session

VALID_PARTS = {"top", "bottom", "one_piece", "full"}


@dataclass
class ResolvedModel:
    path: str
    source: str
    name: str = ""
    info: dict = field(default_factory=dict)


@dataclass
class Plan:
    action: str
    method: str
    part: str
    prompt: str
    references: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "method": self.method,
            "part": self.part,
            "prompt": self.prompt,
            "references": self.references,
            "warnings": self.warnings,
            "details": self.details,
        }


def _resolve_output_dir(settings: Settings, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return settings.output_dir


def _resolve_model(settings: Settings, user_model: str | None, desc: str) -> ResolvedModel:
    if user_model:
        return ResolvedModel(path=user_model, source="user", name=Path(user_model).stem)

    models = load_models(settings.model_lib)
    picked = recommend_model(models, garment_desc=desc)
    image_path = get_model_image(picked, settings.assets_dir)
    if not image_path:
        raise ProviderError(
            f"推荐的模特 {picked.get('name')} 没有可用图片；"
            "请在 assets/models 下补齐图片或使用 --model 指定模特图。"
        )
    return ResolvedModel(
        path=image_path,
        source="library",
        name=str(picked.get("name", "")),
        info=picked,
    )


def _resolve_method(settings: Settings, requested: str) -> str:
    if requested in ("seedream", "qwen"):
        return requested
    if settings.ark_api_key:
        return "seedream"
    if settings.dashscope_api_key:
        return "qwen"
    return "seedream"  # 干跑时给一个默认计划；真实调用会因缺 Key 报错


def _flat_lay_prompt(desc: str) -> str:
    return (
        f"{desc}, flat lay on pure white background, studio lighting, top-down angle, "
        "full garment visible, no wrinkles, sharp details, e-commerce product photo, "
        "no text, no model"
    )


def _save_generated(session: Session, result: GeneratedImage, stage: str, label: str) -> dict:
    if result.url:
        return session.save_url(result.url, stage=stage, label=label)
    if result.b64:
        return session.save_b64(result.b64, stage=stage, label=label)
    raise ProviderError("供应商返回结果既没有 URL 也没有 base64")


def run_tryon(
    settings: Settings,
    garment: str | None = None,
    model: str | None = None,
    desc: str | None = None,
    bottom_garment: str | None = None,
    part: str = "top",
    variants: int = 1,
    method: str = "auto",
    size: str = "2K",
    output_dir: str | None = None,
    fresh_session: bool = False,
    dry_run: bool = False,
) -> tuple[Plan, list[dict]]:
    if part not in VALID_PARTS:
        raise ValueError(f"part 必须是 {sorted(VALID_PARTS)} 之一")
    if not garment and not desc:
        raise ValueError("至少提供 --garment 或 --desc")
    if part == "full" and not bottom_garment:
        raise ValueError("full（上下装）模式需要 --bottom-garment 提供下装图")
    if variants < 1 or variants > 5:
        raise ValueError("--variants 取值范围为 1~5")

    method = _resolve_method(settings, method)
    desc_text = (desc or "").strip() or (Path(garment).stem if garment else "服装")
    resolved_model = _resolve_model(settings, model, desc_text)

    references: list[str] = []
    if not garment:
        # 纯描述：真实运行先用 Seedream 生成服装平铺图
        references = [resolved_model.path]
    else:
        references = [resolved_model.path, garment]
    if part == "full" and bottom_garment:
        references.append(bottom_garment)

    # 当前默认：百炼 qwen-image 图像编辑直接完成试衣；aitryon 为可选的专用引擎
    use_edit_engine = method == "qwen" and settings.tryon_engine == "edit"

    warnings: list[str] = []
    if method == "seedream":
        if not settings.ark_api_key:
            warnings.append("ARK_API_KEY 未配置：干跑可看计划，真实生成会失败")
        warnings.append("提示词图生图的服装保真度低于百炼图像编辑；需要精准贴合请用 --method qwen")
    else:
        if not settings.dashscope_api_key:
            warnings.append("DASHSCOPE_API_KEY / ALIYUN_API_KEY 未配置：真实生成会失败")
        if part == "full" and not bottom_garment:
            warnings.append("百炼试衣 full 模式需要同时提供上装与下装")

    edit_prompt = build_tryon_edit_prompt(part, desc=(desc or "").strip())
    if use_edit_engine:
        prompt = edit_prompt
    else:
        prompt = build_tryon_prompt(desc_text, part)
        if part == "full" and bottom_garment:
            prompt += " 参考图3是下装，请同时穿上图2上装与图3下装。"

    plan = Plan(
        action="tryon",
        method=method,
        part=part,
        prompt=prompt,
        references=references,
        warnings=warnings,
        details={
            "garment": garment,
            "bottom_garment": bottom_garment,
            "desc": desc_text,
            "model": {
                "name": resolved_model.name,
                "source": resolved_model.source,
                "path": resolved_model.path,
            },
            "variants": variants,
            "size": size,
            "engine": "edit" if use_edit_engine else ("aitryon" if method == "qwen" else "seedream"),
            "used_model": settings.tryon_model if use_edit_engine else None,
            "provider_configured": {
                "ark": bool(settings.ark_api_key),
                "dashscope": bool(settings.dashscope_api_key),
            },
        },
    )

    if dry_run:
        return plan, []

    if method == "seedream" and not settings.ark_api_key:
        raise ProviderError("ARK_API_KEY 未配置，无法执行 Seedream 生成")
    if method == "qwen" and not settings.dashscope_api_key:
        raise ProviderError("DASHSCOPE_API_KEY / ALIYUN_API_KEY 未配置，无法执行百炼试衣")

    session = Session(_resolve_output_dir(settings, output_dir), fresh=fresh_session)
    records: list[dict] = []
    started = time.time()

    # 纯描述模式：先生成服装平铺图
    if not garment:
        ark = ArkProvider(settings)
        garment_result = ark.generate_image(
            prompt=_flat_lay_prompt(desc_text),
            size=size,
        )
        garment_record = _save_generated(session, garment_result, stage="garment", label="generated")
        garment = garment_record["path"]
        references = [resolved_model.path, garment]
        plan.references = references
        plan.details["garment"] = garment
        records.append(garment_record)

    if method == "seedream":
        ark = ArkProvider(settings)
        locked_refs = references
        for index in range(variants):
            label = f"result_{index + 1}"
            result = ark.generate_image(
                prompt=prompt,
                reference_images=locked_refs,
                size=size,
            )
            record = _save_generated(session, result, stage="tryon", label=label)
            records.append(record)
            # 只换上装时，用第一张结果作为后续变体的下半身锁定参考
            if part == "top" and index == 0:
                locked_refs = [record["path"], garment]
    else:
        dashscope = DashScopeProvider(settings)
        top_url = garment if part in ("top", "one_piece", "full") else None
        bottom_url = bottom_garment if part == "full" else (garment if part == "bottom" else None)
        edit_refs = [garment] + ([bottom_garment] if part == "full" and bottom_garment else [])
        use_edit = use_edit_engine

        for index in range(variants):
            if not use_edit:
                try:
                    url = dashscope.try_on(
                        person_image=resolved_model.path,
                        top_garment=top_url,
                        bottom_garment=bottom_url,
                    )
                except ProviderError as exc:
                    # 专用试衣模型未开通时，退回通用图像编辑（文档 3.5.4 的兜底策略）
                    if not _model_missing(str(exc)):
                        raise
                    use_edit = True
                    plan.prompt = edit_prompt
                    plan.details["fallback"] = "qwen-image-edit"
                    plan.details["fallback_reason"] = "AI 试衣模型不可用，已切换通用图像编辑"

            if use_edit:
                edit_model, urls = dashscope.edit_image(
                    image=resolved_model.path,
                    instruction=edit_prompt,
                    reference_images=edit_refs,
                    n=1,
                    model=settings.tryon_model if use_edit_engine else None,
                )
                if not urls:
                    raise ProviderError("通用图像编辑未返回图片")
                plan.details["used_model"] = edit_model
                url = urls[0]

            ext = "png" if url.lower().split("?")[0].endswith(".png") else "jpg"
            record = session.save_url(url, stage="tryon", label=f"result_{index + 1}", ext=ext)
            records.append(record)

    elapsed_ms = int((time.time() - started) * 1000)
    session.log_generation(
        action="tryon",
        method=method,
        part=part,
        prompt=prompt,
        references=references,
        outputs=[r["path"] for r in records],
        elapsed_ms=elapsed_ms,
        model=resolved_model.name,
    )
    plan.details["outputs"] = [r["path"] for r in records]
    plan.details["elapsed_ms"] = elapsed_ms
    return plan, records


def run_restyle(
    settings: Settings,
    image: str,
    instructions: list[str] | None = None,
    garment: str | None = None,
    part: str = "top",
    count: int = 1,
    size: str | None = None,
    model: str | None = None,
    output_dir: str | None = None,
    fresh_session: bool = False,
    dry_run: bool = False,
) -> tuple[list[Plan], list[dict]]:
    """AI 换装：指令修改服装，或按参考服装图换衣。

    - instructions 为空且提供 garment：自动生成「让人物穿上图N服装」的指令。
    - 每个 instruction 生成 count 张，失败互不影响。
    """
    if part not in VALID_PARTS:
        raise ValueError(f"part 必须是 {sorted(VALID_PARTS)} 之一")
    if not image:
        raise ValueError("换装需要人物图（--image）")
    if not _is_remote(image) and not Path(image).exists():
        raise ValueError(f"人物图不存在：{image}")
    if garment and not _is_remote(garment) and not Path(garment).exists():
        raise ValueError(f"服装图不存在：{garment}")
    if count < 1 or count > 6:
        raise ValueError("--count 取值范围为 1~6")

    instruction_list = [item.strip() for item in (instructions or []) if item and item.strip()]
    if not instruction_list and not garment:
        raise ValueError("至少提供 --instruction（换装指令）或 --garment（目标服装图）")
    if not instruction_list:
        instruction_list = [""]

    max_dim, min_dim = 2048, 512
    if size:
        normalized = size.replace("x", "*").replace("X", "*")
        try:
            width, height = (int(v) for v in normalized.split("*", 1))
        except ValueError as exc:
            raise ValueError(f"size 格式应为 1024*1024，当前：{size}") from exc
        if not all(min_dim <= v <= max_dim for v in (width, height)):
            raise ValueError(f"size 宽高需在 {min_dim}~{max_dim} 之间，当前：{size}")
        size = normalized

    resolved_model = model or settings.qwen_image_edit_model
    references = [image] + ([garment] if garment else [])

    plans: list[Plan] = []
    for instruction in instruction_list:
        prompt = build_restyle_prompt(
            instruction=instruction,
            part=part,
            has_garment_reference=bool(garment),
            garment_ref_index=2,
        )
        warnings: list[str] = []
        if not settings.dashscope_api_key:
            warnings.append("DASHSCOPE_API_KEY 未配置：干跑可看计划，真实生成会失败")
        if not garment and any(k in instruction for k in ("换场景", "背景")):
            warnings.append("指令涉及背景时，会与「保持背景不变」的保护前缀冲突，建议明确写「只换场景/背景」")
        plans.append(
            Plan(
                action="restyle",
                method="qwen-image-edit",
                part=part,
                prompt=prompt,
                references=references,
                warnings=warnings,
                details={
                    "instruction": instruction,
                    "garment": garment,
                    "count": count,
                    "size": size,
                    "model": resolved_model,
                    "fallbacks": list(settings.qwen_image_edit_fallbacks),
                },
            )
        )

    if dry_run:
        return plans, []

    if not settings.dashscope_api_key:
        raise ProviderError("DASHSCOPE_API_KEY / ALIYUN_API_KEY 未配置，无法执行 AI 换装")

    dashscope = DashScopeProvider(settings)
    session = Session(_resolve_output_dir(settings, output_dir), fresh=fresh_session)
    records: list[dict] = []
    started = time.time()

    for plan_index, plan in enumerate(plans, 1):
        used_model, urls = dashscope.edit_image(
            image=image,
            instruction=plan.prompt,
            reference_images=[garment] if garment else None,
            n=count,
            size=size,
            model=model,
        )
        plan.details["used_model"] = used_model
        plan.details["outputs"] = []
        for image_index, url in enumerate(urls, 1):
            record = session.save_url(
                url,
                stage="restyle",
                label=f"{plan_index:02d}_{image_index}",
                ext="png",  # qwen-image 编辑结果固定为 PNG
            )
            records.append(record)
            plan.details["outputs"].append(record["path"])

    elapsed_ms = int((time.time() - started) * 1000)
    session.log_generation(
        action="restyle",
        part=part,
        instructions=instruction_list,
        garment=garment,
        prompt=plans[0].prompt if plans else "",
        references=references,
        outputs=[r["path"] for r in records],
        elapsed_ms=elapsed_ms,
        model=plans[0].details.get("used_model") if plans else resolved_model,
    )
    return plans, records


def _is_remote(path: str) -> bool:
    return path.startswith(("http://", "https://", "data:"))


def _model_missing(message: str) -> bool:
    text = message.lower()
    return any(
        marker in text
        for marker in ("model not exist", "model_not_found", "model not found",
                       "does not exist", "invalid model", "模型不存在")
    )


def _collect_angles(preset: str) -> list[dict]:
    keys = [item.strip() for item in preset.split(",") if item.strip()]
    angles: list[dict] = []
    for key in keys:
        group = ANGLE_PRESETS.get(key)
        if group:
            angles.extend(group["angles"])
    if not angles:
        angles = ANGLE_PRESETS["ecommerce"]["angles"]
    return angles


def run_angles(
    settings: Settings,
    garment: str,
    model: str,
    preset: str = "ecommerce",
    part: str = "top",
    base_desc: str = "",
    limit: int | None = None,
    size: str = "2K",
    output_dir: str | None = None,
    fresh_session: bool = False,
    dry_run: bool = False,
) -> tuple[list[Plan], list[dict]]:
    if part not in VALID_PARTS:
        raise ValueError(f"part 必须是 {sorted(VALID_PARTS)} 之一")
    angles = _collect_angles(preset)
    if limit:
        angles = angles[:limit]

    plans: list[Plan] = []
    for angle in angles:
        prompt = build_angle_prompt(part, angle["suffix"], base_desc)
        plans.append(
            Plan(
                action="angle",
                method="seedream",
                part=part,
                prompt=prompt,
                references=[model, garment],
                warnings=[] if settings.ark_api_key else ["ARK_API_KEY 未配置：真实生成会失败"],
                details={"scene": angle["scene"], "label": angle["label"]},
            )
        )

    if dry_run:
        return plans, []
    if not settings.ark_api_key:
        raise ProviderError("ARK_API_KEY 未配置，无法执行多角度生成")

    ark = ArkProvider(settings)
    session = Session(_resolve_output_dir(settings, output_dir), fresh=fresh_session)
    records: list[dict] = []
    started = time.time()
    for plan, angle in zip(plans, angles):
        result = ark.generate_image(
            prompt=plan.prompt,
            reference_images=[model, garment],
            size=size,
        )
        record = _save_generated(session, result, stage="tryon", label=f"angle_{angle['label']}")
        records.append(record)
        plan.details["output"] = record["path"]

    session.log_generation(
        action="angles",
        preset=preset,
        part=part,
        references=[model, garment],
        outputs=[r["path"] for r in records],
        elapsed_ms=int((time.time() - started) * 1000),
    )
    return plans, records


def run_video(
    settings: Settings,
    image: str | None = None,
    images: list[str] | None = None,
    prompt: str | None = None,
    garment_desc: str = "服装",
    duration: int = 5,
    ratio: str = "9:16",
    generate_audio: bool = False,
    method: str = "auto",
    resolution: str = "480P",
    output_dir: str | None = None,
    fresh_session: bool = False,
    dry_run: bool = False,
) -> tuple[Plan, list[dict]]:
    refs = list(images or [])
    if image:
        refs.insert(0, image)
    if not refs:
        raise ValueError("视频生成至少需要 --image 或 --images")
    if len(refs) > 4:
        raise ValueError("多图视频最多支持 4 张参考图（Ark LITE 限制）")

    multi = len(refs) > 1
    if method == "auto":
        method = "seedance" if multi or not settings.dashscope_api_key else "wan"
    if method not in {"wan", "seedance"}:
        raise ValueError("method 必须是 auto / wan / seedance")
    if method == "wan" and multi:
        raise ValueError("万相图生视频仅支持单张首帧；多图请使用 seedance")

    if method == "wan":
        prompt = prompt or build_wan_video_prompt(garment_desc)
        model = settings.video_model
        method_label = "wan-i2v"
        warnings = [] if settings.dashscope_api_key else ["DASHSCOPE_API_KEY 未配置：真实生成会失败"]
    else:
        prompt = prompt or build_video_prompt(garment_desc, multi=multi)
        model = settings.ark_video_model_pro if len(refs) == 1 else settings.ark_video_model_lite
        method_label = "seedance"
        warnings = [] if settings.ark_api_key else ["ARK_API_KEY 未配置：真实生成会失败"]

    plan = Plan(
        action="video",
        method=method_label,
        part="video",
        prompt=prompt,
        references=refs,
        warnings=warnings,
        details={
            "provider": method,
            "model": model,
            "duration": duration,
            "ratio": ratio,
            "resolution": resolution,
            "generate_audio": generate_audio,
        },
    )
    if dry_run:
        return plan, []

    session = Session(_resolve_output_dir(settings, output_dir), fresh=fresh_session)
    started = time.time()
    if method == "wan":
        if not settings.dashscope_api_key:
            raise ProviderError("DASHSCOPE_API_KEY 未配置，无法执行万相图生视频")
        dashscope = DashScopeProvider(settings)
        url = dashscope.generate_video(
            image=refs[0],
            prompt=prompt,
            model=model,
            resolution=resolution,
            duration=duration,
        )
        label = "wan"
    else:
        if not settings.ark_api_key:
            raise ProviderError("ARK_API_KEY 未配置，无法执行 Seedance 视频生成")
        ark = ArkProvider(settings)
        url = ark.generate_video(
            prompt=prompt,
            images=refs if multi else None,
            image=None if multi else refs[0],
            duration=duration,
            ratio=ratio,
            generate_audio=generate_audio,
        )
        label = "multi" if multi else "i2v"

    record = session.save_video_url(url, label=label)
    session.log_generation(
        action="video",
        prompt=prompt,
        references=refs,
        outputs=[record["path"]],
        elapsed_ms=int((time.time() - started) * 1000),
        model=model,
    )
    plan.details["output"] = record["path"]
    return plan, [record]
