"""火山方舟（Ark）适配器：Seedream 生图 / Seedance 生视频。

Ark 提供 OpenAI 兼容接口，生图使用 openai SDK；
生视频使用 `/contents/generations/tasks` 异步任务接口。
"""
from __future__ import annotations

import base64
import json
import mimetypes
import time
import urllib.error
import urllib.request
from pathlib import Path

from config import Settings
from .base import GeneratedImage, ProviderError, ProviderNotConfigured

_IMAGE_EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


def image_to_input(path_or_url: str) -> str:
    """Ark 接受公网 URL 或 base64 data URI；本地文件自动转 data URI。"""
    if path_or_url.startswith(("http://", "https://", "data:")):
        return path_or_url

    path = Path(path_or_url)
    if not path.exists():
        raise ProviderError(f"图片不存在：{path}")
    mime = _IMAGE_EXT_MIME.get(path.suffix.lower())
    if not mime:
        mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    payload = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{payload}"


class ArkProvider:
    name = "ark"

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.ark_api_key)

    def _client(self):
        if not self.configured:
            raise ProviderNotConfigured(
                "ARK_API_KEY 未配置。在 replica/.env 中填写火山方舟 API Key。"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError("缺少依赖 openai，请先执行：pip install openai") from exc
        return OpenAI(
            base_url=self.settings.ark_base_url,
            api_key=self.settings.ark_api_key,
        )

    # ── 生图 ──────────────────────────────────────────────
    def generate_image(
        self,
        prompt: str,
        reference_images: list[str] | None = None,
        size: str = "2K",
        model: str | None = None,
    ) -> GeneratedImage:
        """Seedream 生图。有参考图时传 `image` 列表，锁定人物/服装外观。"""
        client = self._client()
        model = model or self.settings.ark_image_model
        extra_body: dict = {"watermark": False}
        refs = reference_images or []
        if refs:
            inputs = [image_to_input(item) for item in refs]
            # 单图时 Ark 也接受字符串；多图必须传数组
            extra_body["image"] = inputs[0] if len(inputs) == 1 else inputs
            extra_body["sequential_image_generation"] = "disabled"

        try:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                response_format="url",
                extra_body=extra_body,
            )
        except Exception as exc:  # openai 的异常类型随版本变化，统一包装
            raise ProviderError(f"Seedream 生图失败：{exc}") from exc

        if not response.data:
            raise ProviderError("Seedream 返回空结果")
        first = response.data[0]
        url = getattr(first, "url", None)
        b64 = getattr(first, "b64_json", None)
        if not url and not b64:
            raise ProviderError("Seedream 返回结果中没有 url/b64_json")
        return GeneratedImage(url=url, b64=b64, provider=self.name, model=model)

    # ── 生视频 ────────────────────────────────────────────
    def generate_video(
        self,
        prompt: str,
        image: str | None = None,
        images: list[str] | None = None,
        duration: int = 5,
        ratio: str = "9:16",
        generate_audio: bool = False,
        timeout: int = 300,
    ) -> str:
        """Seedance 图生视频。

        - 单图 / 首帧：使用 PRO 模型
        - 多参考图：使用 LITE 模型（reference_image 仅 LITE 支持）
        """
        refs = list(images or [])
        if image:
            refs.insert(0, image)
        if not refs:
            raise ProviderError("视频生成至少需要一张图片")

        model = (
            self.settings.ark_video_model_pro
            if len(refs) == 1
            else self.settings.ark_video_model_lite
        )

        content: list[dict] = [{"type": "text", "text": prompt}]
        for idx, ref in enumerate(refs):
            item = {"type": "image_url", "image_url": {"url": image_to_input(ref)}}
            if len(refs) > 1:
                item["role"] = "reference_image"
            elif idx == 0 and image is None:
                item["role"] = "reference_image"
            content.append(item)

        payload = {
            "model": model,
            "content": content,
            "duration": duration,
            "ratio": ratio,
            "watermark": False,
        }
        if generate_audio:
            payload["generate_audio"] = True

        result = self._post("/contents/generations/tasks", payload)
        task_id = result.get("id") or result.get("task_id")
        if not task_id:
            raise ProviderError(f"视频任务提交失败，响应：{result}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(5)
            status = self._get(f"/contents/generations/tasks/{task_id}")
            state = str(status.get("status", "")).lower()
            if state in ("succeeded", "success"):
                for item in status.get("content", []) or []:
                    if isinstance(item, dict) and item.get("video_url"):
                        return item["video_url"]
                direct = status.get("video_url") or status.get("output", {}).get("video_url")
                if direct:
                    return direct
                raise ProviderError(f"视频任务成功但未找到 video_url：{json.dumps(status)[:500]}")
            if state in ("failed", "cancelled"):
                raise ProviderError(f"视频任务失败：{status.get('error', status)}")
        raise ProviderError(f"视频任务超时（{timeout}s），task_id={task_id}")

    # ── HTTP helpers ──────────────────────────────────────
    def _post(self, path: str, payload: dict) -> dict:
        if not self.configured:
            raise ProviderNotConfigured("ARK_API_KEY 未配置")
        req = urllib.request.Request(
            f"{self.settings.ark_base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.ark_api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(f"Ark HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Ark 网络错误：{exc}") from exc

    def _get(self, path: str) -> dict:
        if not self.configured:
            raise ProviderNotConfigured("ARK_API_KEY 未配置")
        req = urllib.request.Request(
            f"{self.settings.ark_base_url}{path}",
            headers={"Authorization": f"Bearer {self.settings.ark_api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(f"Ark 轮询 HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Ark 轮询网络错误：{exc}") from exc
