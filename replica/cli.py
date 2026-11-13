"""shop-tryon-skill 复刻版 CLI。

用法：
  python cli.py config
  python cli.py models list
  python cli.py models recommend "JK制服"
  python cli.py analyze garment.jpg --json
  python cli.py run --garment g.jpg --desc "白色T恤" --part top --dry-run
  python cli.py run --garment g.jpg --model m.jpg --part one_piece --variants 2
  python cli.py angles --garment g.jpg --model m.jpg --preset ecommerce
  python cli.py restyle --image photo.jpg --instruction "换成米色针织开衫"
  python cli.py restyle --image photo.jpg --garment g.jpg --part top
  python cli.py video --image result.jpg --prompt "模特缓慢转身"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 避免 Windows GBK 控制台因 emoji / 生僻字符崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from config import ROOT, get_settings, looks_like_aliyun_access_key
from providers import DashScopeProvider, ProviderError
from core.model_library import (
    format_model_list,
    get_model_image,
    list_models,
    load_models,
    recommend_model,
)
from core.pipeline import run_angles, run_restyle, run_tryon, run_video
from core.prompts import GARMENT_ANALYSIS_PROMPT


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _print_plan(plan) -> None:
    info = plan.to_dict() if hasattr(plan, "to_dict") else plan
    print("\n" + "=" * 62)
    print(f"动作: {info.get('action')}   方法: {info.get('method')}   部位: {info.get('part')}")
    print("=" * 62)
    details = info.get("details", {})
    model = details.get("model")
    if isinstance(model, dict):
        print(f"模特: {model.get('name')}（{model.get('source')}）")
        print(f"      {model.get('path')}")
    if details.get("garment"):
        print(f"服装: {details['garment']}")
    if info.get("references"):
        print("参考图:")
        for ref in info["references"]:
            print(f"  - {ref}")
    if details.get("warnings"):
        print("提示:")
        for warning in details["warnings"]:
            print(f"  ! {warning}")
    if info.get("warnings"):
        print("提示:")
        for warning in info["warnings"]:
            print(f"  ! {warning}")
    print("\nPrompt:")
    print(info.get("prompt", ""))
    if details:
        print("\n详情:")
        _print_json(details)


def _print_records(records: list[dict]) -> None:
    if not records:
        return
    print("\n生成结果:")
    for index, record in enumerate(records, 1):
        print(f"  [{index}] {record.get('stage')}  {record.get('path')}")
        if record.get("url"):
            print(f"      URL: {record['url'][:80]}")


# ── commands ─────────────────────────────────────────────
def cmd_config(args) -> int:
    settings = get_settings()
    _print_json(settings.provider_status())
    missing = []
    if not settings.ark_api_key:
        missing.append("ARK_API_KEY（Seedream 生图 / Seedance 视频）")
    if not settings.dashscope_api_key:
        missing.append("DASHSCOPE_API_KEY 或 ALIYUN_API_KEY（AI 试衣 / qwen-vl）")
    if settings.dashscope_api_key and looks_like_aliyun_access_key(settings.dashscope_api_key):
        print(
            "\n注意：DASHSCOPE_API_KEY 填的是 AccessKey ID（LTAI...），"
            "它不能调用百炼模型。\n请改用百炼控制台创建的 sk- 开头 API Key。"
        )
    if missing:
        print("\n未配置:")
        for item in missing:
            print(f"  - {item}")
        print(f"\n复制 {ROOT / '.env.example'} 为 {ROOT / '.env'} 后填写。")
    return 0


def cmd_models(args) -> int:
    settings = get_settings()
    models = load_models(settings.model_lib)

    if args.models_action == "list":
        print(format_model_list(models))
        return 0

    if args.models_action == "recommend":
        picked = recommend_model(models, garment_desc=args.desc)
        image = get_model_image(picked, settings.assets_dir)
        print(f"推荐模特: {picked.get('name')} ({picked.get('style')}, "
              f"{picked.get('height')}, {picked.get('bodyType')})")
        print(f"ID: {picked.get('id')}")
        print(f"图片: {image}")
        if picked.get("desc"):
            print(f"说明: {picked['desc']}")
        return 0

    raise SystemExit("用法: python cli.py models list | models recommend <描述>")


def cmd_analyze(args) -> int:
    settings = get_settings()
    provider = DashScopeProvider(settings)
    result = provider.analyze_garment(args.image, args.prompt or GARMENT_ANALYSIS_PROMPT)
    if args.json:
        _print_json(result)
        return 0 if "error" not in result else 1

    if "error" in result:
        print(f"分析失败: {result['error']}")
        if result.get("raw"):
            print(result["raw"])
        return 1

    print("服装分析结果")
    print(f"  类型: {result.get('type', '未知')}")
    print(f"  分类: {result.get('category', '未知')}")
    print(f"  颜色: {result.get('color', '未知')}")
    print(f"  面料: {result.get('fabric', '未知')}")
    print(f"  风格: {', '.join(result.get('style', []))}")
    print(f"  适合: {result.get('gender', '未知')}")
    print(f"  季节: {result.get('season', '未知')}")
    print(f"  场景: {result.get('occasion', '未知')}")
    print(f"  描述: {result.get('description', '')}")
    return 0


def cmd_run(args) -> int:
    settings = get_settings()
    plan, records = run_tryon(
        settings=settings,
        garment=args.garment,
        model=args.model,
        desc=args.desc,
        bottom_garment=args.bottom_garment,
        part=args.part,
        variants=args.variants,
        method=args.method,
        size=args.size,
        output_dir=args.output_dir,
        fresh_session=args.new_session,
        dry_run=args.dry_run,
    )
    _print_plan(plan)
    if args.dry_run:
        print("\n[DRY-RUN] 未调用任何 API，未生成图片。")
    else:
        _print_records(records)
    return 0


def cmd_restyle(args) -> int:
    settings = get_settings()
    plans, records = run_restyle(
        settings=settings,
        image=args.image,
        instructions=args.instruction,
        garment=args.garment,
        part=args.part,
        count=args.count,
        size=args.size,
        model=args.model,
        output_dir=args.output_dir,
        fresh_session=args.new_session,
        dry_run=args.dry_run,
    )
    for index, plan in enumerate(plans, 1):
        label = plan.details.get("instruction") or "按参考服装图换衣"
        print(f"\n--- 换装 {index}: {label} ---")
        _print_plan(plan)
    if args.dry_run:
        print("\n[DRY-RUN] 未调用任何 API，未生成图片。")
    else:
        _print_records(records)
    return 0


def cmd_angles(args) -> int:
    settings = get_settings()
    plans, records = run_angles(
        settings=settings,
        garment=args.garment,
        model=args.model,
        preset=args.preset,
        part=args.part,
        base_desc=args.desc or "",
        limit=args.limit,
        size=args.size,
        output_dir=args.output_dir,
        fresh_session=args.new_session,
        dry_run=args.dry_run,
    )
    for index, plan in enumerate(plans, 1):
        print(f"\n--- 角度 {index}: {plan.details.get('scene')} ---")
        _print_plan(plan)
    if args.dry_run:
        print("\n[DRY-RUN] 未调用任何 API，未生成图片。")
    else:
        _print_records(records)
    return 0


def cmd_video(args) -> int:
    settings = get_settings()
    plan, records = run_video(
        settings=settings,
        image=args.image,
        images=args.images,
        prompt=args.prompt,
        garment_desc=args.desc or "服装",
        duration=args.duration,
        ratio=args.ratio,
        generate_audio=args.audio,
        output_dir=args.output_dir,
        fresh_session=args.new_session,
        dry_run=args.dry_run,
    )
    _print_plan(plan)
    if args.dry_run:
        print("\n[DRY-RUN] 未调用任何 API，未生成视频。")
    else:
        _print_records(records)
    return 0


# ── parser ───────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="replica",
        description="shop-tryon-skill 复刻版：服装图/描述 -> AI 模特试穿 -> 换装 -> 多角度 -> 视频",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_config = sub.add_parser("config", help="查看 Provider 配置状态（不显示密钥）")
    p_config.set_defaults(func=cmd_config)

    p_models = sub.add_parser("models", help="内置模特库")
    p_models.add_argument("models_action", choices=["list", "recommend"])
    p_models.add_argument("desc", nargs="?", default="", help="recommend 时的服装描述")
    p_models.set_defaults(func=cmd_models)

    p_analyze = sub.add_parser("analyze", help="qwen-vl 分析服装图")
    p_analyze.add_argument("image", help="本地图片或公网 URL")
    p_analyze.add_argument("--json", action="store_true", help="输出 JSON")
    p_analyze.add_argument("--prompt", default=None, help="自定义分析提示词")
    p_analyze.set_defaults(func=cmd_analyze)

    p_run = sub.add_parser("run", help="试穿主流程")
    p_run.add_argument("--garment", help="服装图路径或 URL")
    p_run.add_argument("--bottom-garment", help="下装图（part=full 时必填）")
    p_run.add_argument("--model", help="模特图路径或 URL；不传则从模特库推荐")
    p_run.add_argument("--desc", help="服装文字描述（无服装图时用于生成服装图）")
    p_run.add_argument("--part", default="top", choices=["top", "bottom", "one_piece", "full"])
    p_run.add_argument("--variants", type=int, default=1, help="生成数量 1~5")
    p_run.add_argument("--method", default="auto", choices=["auto", "seedream", "qwen"],
                       help="auto 优先 Seedream；qwen 走百炼图像编辑试衣（TRYON_ENGINE=edit）")
    p_run.add_argument("--size", default="2K", help="Seedream 尺寸，如 2K / 1024x1024")
    p_run.add_argument("--output-dir", default=None)
    p_run.add_argument("--new-session", action="store_true")
    p_run.add_argument("--dry-run", action="store_true", help="只打印计划，不调用 API")
    p_run.set_defaults(func=cmd_run)

    p_restyle = sub.add_parser("restyle", help="AI 换装：指令换色/换款/加外套，或按服装图换衣")
    p_restyle.add_argument("--image", required=True, help="人物图路径或 URL")
    p_restyle.add_argument("--instruction", action="append", default=None,
                           help="换装指令，可重复传多条（换色/换款/加外套）")
    p_restyle.add_argument("--garment", help="目标服装图；提供后按图换衣")
    p_restyle.add_argument("--part", default="top", choices=["top", "bottom", "one_piece", "full"])
    p_restyle.add_argument("--count", type=int, default=1, help="每条指令生成数量 1~6")
    p_restyle.add_argument("--size", default=None, help="输出尺寸，如 1024*1024（默认跟随原图）")
    p_restyle.add_argument("--model", default=None,
                           help="图像编辑模型，默认 qwen-image-3.0；不存在时自动降级")
    p_restyle.add_argument("--output-dir", default=None)
    p_restyle.add_argument("--new-session", action="store_true")
    p_restyle.add_argument("--dry-run", action="store_true", help="只打印计划，不调用 API")
    p_restyle.set_defaults(func=cmd_restyle)

    p_angles = sub.add_parser("angles", help="同模特同服装多角度")
    p_angles.add_argument("--garment", required=True)
    p_angles.add_argument("--model", required=True)
    p_angles.add_argument("--preset", default="ecommerce",
                          help="ecommerce/catwalk/detail/lifestyle，可逗号组合")
    p_angles.add_argument("--part", default="top", choices=["top", "bottom", "one_piece", "full"])
    p_angles.add_argument("--desc", default="", help="补充服装描述")
    p_angles.add_argument("--limit", type=int, default=None, help="只生成前 N 个角度")
    p_angles.add_argument("--size", default="2K")
    p_angles.add_argument("--output-dir", default=None)
    p_angles.add_argument("--new-session", action="store_true")
    p_angles.add_argument("--dry-run", action="store_true")
    p_angles.set_defaults(func=cmd_angles)

    p_video = sub.add_parser("video", help="Seedance 图生视频")
    group = p_video.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", help="单张首帧")
    group.add_argument("--images", nargs="+", help="多张参考图（最多 4 张）")
    p_video.add_argument("--prompt", help="视频描述；不传则用内置模板")
    p_video.add_argument("--desc", default="服装", help="服装描述，用于内置 prompt")
    p_video.add_argument("--duration", type=int, default=5)
    p_video.add_argument("--ratio", default="9:16", choices=["9:16", "16:9", "1:1"])
    p_video.add_argument("--audio", action="store_true", help="生成音效（仅单图 PRO）")
    p_video.add_argument("--output-dir", default=None)
    p_video.add_argument("--new-session", action="store_true")
    p_video.add_argument("--dry-run", action="store_true")
    p_video.set_defaults(func=cmd_video)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (ProviderError, ValueError, FileNotFoundError) as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
