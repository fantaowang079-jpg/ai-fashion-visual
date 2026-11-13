"""Provider 基类、结果类型与异常。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GeneratedImage:
    """统一图片结果：URL 或 base64 二选一。"""

    url: str | None = None
    b64: str | None = None
    provider: str = ""
    model: str = ""


class ProviderError(RuntimeError):
    """供应商调用失败（可展示给用户的错误）。"""


class ProviderNotConfigured(ProviderError):
    """缺少 API Key 或必要配置。"""
