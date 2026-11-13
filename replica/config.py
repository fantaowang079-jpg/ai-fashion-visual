"""集中配置：读取 .env、解析路径、暴露 Settings。

不依赖 python-dotenv，保持最小依赖。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    """极简 .env 解析：KEY=VALUE，跳过注释；不覆盖已存在的环境变量。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def looks_like_aliyun_access_key(value: str) -> bool:
    """阿里云 RAM AccessKey ID 通常以 LTAI 开头；它不能用于百炼模型调用。"""
    return value.startswith("LTAI")


@dataclass(frozen=True)
class Settings:
    # 火山方舟（Seedream / Seedance）
    ark_api_key: str
    ark_base_url: str
    ark_image_model: str
    ark_video_model_pro: str
    ark_video_model_lite: str

    # 阿里云百炼（AI 试衣 / qwen-vl）
    dashscope_api_key: str
    dashscope_base_url: str
    dashscope_native_base_url: str
    qwen_vl_model: str
    qwen_image_edit_model: str
    qwen_image_edit_fallbacks: tuple[str, ...]
    tryon_model: str
    tryon_engine: str
    stylist_model: str
    video_model: str

    # 阿里云 BSS（账户余额查询；与百炼 sk- Key 不同）
    aliyun_access_key_id: str
    aliyun_access_key_secret: str
    bss_endpoint: str
    balance_ui_enabled: bool

    # 路径
    output_dir: Path
    model_lib: Path
    assets_dir: Path

    def provider_status(self) -> dict:
        """给 CLI 展示的配置状态，不包含任何密钥明文。"""
        return {
            "ark": {
                "configured": bool(self.ark_api_key),
                "base_url": self.ark_base_url,
                "image_model": self.ark_image_model,
                "video_model_pro": self.ark_video_model_pro,
                "video_model_lite": self.ark_video_model_lite,
            },
            "dashscope": {
                "configured": bool(self.dashscope_api_key),
                "credential_warning": (
                    "检测到 AccessKey ID（LTAI...），百炼模型调用需要 sk- 开头的 API Key"
                    if looks_like_aliyun_access_key(self.dashscope_api_key)
                    else ""
                ),
                "base_url": self.dashscope_base_url,
                "native_base_url": self.dashscope_native_base_url,
                "qwen_vl_model": self.qwen_vl_model,
                "qwen_image_edit_model": self.qwen_image_edit_model,
                "qwen_image_edit_fallbacks": list(self.qwen_image_edit_fallbacks),
                "tryon_model": self.tryon_model,
                "tryon_engine": self.tryon_engine,
                "stylist_model": self.stylist_model,
                "video_model": self.video_model,
                "balance": {
                    "configured": bool(
                        self.aliyun_access_key_id and self.aliyun_access_key_secret
                    ),
                    "endpoint": self.bss_endpoint,
                    "ui_enabled": self.balance_ui_enabled,
                },
            },
            "output_dir": str(self.output_dir),
            "model_lib": str(self.model_lib),
            "model_asset_dir": str(self.assets_dir / "models"),
        }


def _derive_native_base(compatible_base: str) -> str:
    """AI 试衣走原生 /api/v1，不使用 compatible-mode 地址。

    业务空间专属地址形如：
      https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
    原生地址则为：
      https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/api/v1
    """
    explicit = _env("DASHSCOPE_NATIVE_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    if ".maas.aliyuncs.com" in compatible_base:
        root = compatible_base.split("/compatible-mode/")[0].rstrip("/")
        return f"{root}/api/v1"
    return "https://dashscope.aliyuncs.com/api/v1"


def get_settings() -> Settings:
    raw_output = _env("TRYON_OUTPUT_DIR")
    output_dir = Path(raw_output).expanduser() if raw_output else ROOT / "output"
    if not output_dir.is_absolute():
        output_dir = (ROOT / output_dir).resolve()

    model_lib = ROOT / "assets" / "models.json"
    compatible_base = _env("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    return Settings(
        ark_api_key=_env("ARK_API_KEY"),
        ark_base_url=_env("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        ark_image_model=_env("ARK_IMAGE_MODEL", "doubao-seedream-5-0-260128"),
        ark_video_model_pro=_env("ARK_VIDEO_MODEL_PRO", "doubao-seedance-1-5-pro-251215"),
        ark_video_model_lite=_env("ARK_VIDEO_MODEL_LITE", "doubao-seedance-1-0-lite-i2v-250428"),
        dashscope_api_key=_env("DASHSCOPE_API_KEY") or _env("ALIYUN_API_KEY"),
        dashscope_base_url=compatible_base,
        dashscope_native_base_url=_derive_native_base(compatible_base),
        qwen_vl_model=_env("QWEN_VL_MODEL", "qwen-vl-max"),
        qwen_image_edit_model=_env("QWEN_IMAGE_EDIT_MODEL", "qwen-image-3.0"),
        qwen_image_edit_fallbacks=tuple(
            item.strip()
            for item in _env(
                "QWEN_IMAGE_EDIT_FALLBACKS", "qwen-image-2.1-pro,qwen-image-2.0"
            ).split(",")
            if item.strip()
        ),
        tryon_model=_env("TRYON_MODEL", "qwen-image-3.0"),
        stylist_model=_env("STYLIST_MODEL", "qwen-plus"),
        video_model=_env("WAN_VIDEO_MODEL", "wan2.5-i2v-preview"),
        aliyun_access_key_id=_env("ALIYUN_ACCESS_KEY_ID"),
        aliyun_access_key_secret=_env("ALIYUN_ACCESS_KEY_SECRET"),
        bss_endpoint=_env("BSS_ENDPOINT", "https://business.aliyuncs.com"),
        balance_ui_enabled=_env("BALANCE_UI_ENABLED", "0").lower()
        in {"1", "true", "yes", "on"},
        tryon_engine=(
            _env("TRYON_ENGINE", "edit").lower()
            if _env("TRYON_ENGINE", "edit").lower() in {"edit", "aitryon"}
            else "edit"
        ),
        output_dir=output_dir,
        model_lib=model_lib,
        assets_dir=ROOT / "assets",
    )
