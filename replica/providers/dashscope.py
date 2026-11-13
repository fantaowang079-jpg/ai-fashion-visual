"""阿里云百炼适配器：AI 试衣、AI 换装、服装解析、qwen-vl 服装分析。

- 试衣/解析：DashScope 原生异步任务接口（提交 -> 轮询）
- 换装/图像编辑：multimodal-generation 同步接口（qwen-image 系列）
- 视觉分析：OpenAI 兼容接口（qwen-vl-max）
"""
from __future__ import annotations

import base64
import json
import mimetypes
import time
import urllib.error
import urllib.request
from pathlib import Path

from config import Settings, looks_like_aliyun_access_key
from .base import ProviderError, ProviderNotConfigured


_IMAGE_EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
}


def _image_input(path_or_url: str) -> str:
    """本地图片转 base64 data URI；URL 原样返回。"""
    if path_or_url.startswith(("http://", "https://", "data:")):
        return path_or_url
    path = Path(path_or_url)
    if not path.exists():
        raise ProviderError(f"图片不存在：{path}")
    mime = _IMAGE_EXT_MIME.get(path.suffix.lower())
    if not mime:
        mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


class DashScopeProvider:
    name = "dashscope"

    def __init__(self, settings: Settings):
        self.settings = settings
        native = settings.dashscope_native_base_url.rstrip("/")
        self._submit_url = f"{native}/services/aigc/image2image/image-synthesis/"
        self._video_submit_url = f"{native}/services/aigc/video-generation/video-synthesis"
        self._edit_url = f"{native}/services/aigc/multimodal-generation/generation"
        self._task_url = f"{native}/tasks/{{task_id}}"

    @property
    def configured(self) -> bool:
        return bool(self.settings.dashscope_api_key)

    def _check(self) -> None:
        if not self.configured:
            raise ProviderNotConfigured(
                "DASHSCOPE_API_KEY / ALIYUN_API_KEY 未配置。在 replica/.env 中填写百炼 API Key。"
            )
        if looks_like_aliyun_access_key(self.settings.dashscope_api_key):
            raise ProviderNotConfigured(
                "检测到阿里云 AccessKey ID（LTAI...），它不是百炼模型 API Key。\n"
                "请到百炼控制台「API-KEY 管理」创建 sk- 开头的 API Key，"
                "填入 DASHSCOPE_API_KEY；AccessKey 只能调阿里云 OpenAPI/OSS。"
            )

    # ── 服装视觉分析 ──────────────────────────────────────
    def analyze_garment(self, image: str, prompt: str) -> dict:
        """qwen-vl 分析服装图，返回结构化 JSON。"""
        self._check()
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError("缺少依赖 openai，请先执行：pip install openai") from exc

        client = OpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.dashscope_base_url,
        )
        try:
            completion = client.chat.completions.create(
                model=self.settings.qwen_vl_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": _image_input(image)}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
        except Exception as exc:
            raise ProviderError(f"服装分析调用失败：{exc}") from exc

        raw = (completion.choices[0].message.content or "").strip()
        return self._parse_json_loose(raw)

    @staticmethod
    def _parse_json_loose(raw: str) -> dict:
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1]
        if "```" in text:
            text = text.split("```", 1)[0]
        text = text.strip()
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {"error": "模型返回的不是 JSON 对象", "raw": raw}
        except json.JSONDecodeError:
            return {"error": "JSON 解析失败", "raw": raw}

    # ── AI 换装 / 图像编辑 ─────────────────────────────────
    def edit_image(
        self,
        image: str,
        instruction: str,
        reference_images: list[str] | None = None,
        n: int = 1,
        size: str | None = None,
        model: str | None = None,
        fallback_models: list[str] | tuple[str, ...] | None = None,
        watermark: bool = False,
    ) -> tuple[str, list[str]]:
        """指令换装：保留人物与背景，只改服装。

        调用 qwen-image 系列的同步图像编辑接口。`image` 是人物图，
        `reference_images` 可追加目标服装图（最多 2 张，接口上限为 3 张）。
        返回 (实际使用的模型, 结果图片 URL 列表)。
        """
        self._check()
        if not instruction.strip():
            raise ProviderError("换装指令不能为空")
        if n < 1 or n > 6:
            raise ProviderError("n（生成数量）取值范围为 1~6")

        refs = [image, *(reference_images or [])]
        if len(refs) > 3:
            raise ProviderError("百炼图像编辑最多支持 3 张输入图（人物图 + 最多 2 张服装图）")

        content = [{"image": _image_input(ref)} for ref in refs]
        content.append({"text": instruction.strip()})

        parameters: dict = {"n": int(n), "watermark": bool(watermark), "prompt_extend": True}
        if size:
            parameters["size"] = size.replace("x", "*").replace("X", "*")

        candidates = [model or self.settings.qwen_image_edit_model]
        for item in fallback_models if fallback_models is not None else self.settings.qwen_image_edit_fallbacks:
            if item and item not in candidates:
                candidates.append(item)

        last_error: ProviderError | None = None
        for candidate in candidates:
            try:
                output = self._post_sync(
                    {
                        "model": candidate,
                        "input": {"messages": [{"role": "user", "content": content}]},
                        "parameters": parameters,
                    }
                )
            except ProviderError as exc:
                last_error = exc
                # 仅当模型不存在时才切换备选；额度/网络/参数错误直接抛出，避免重复计费
                if len(candidates) > 1 and not self._is_model_missing(str(exc)):
                    raise
                continue

            urls = self._extract_image_urls(output)
            if urls:
                return candidate, urls
            last_error = ProviderError(f"图像编辑任务成功但未返回图片：{json.dumps(output)[:500]}")
            break

        raise last_error or ProviderError("图像编辑失败：没有可用的模型")

    @staticmethod
    def _is_model_missing(message: str) -> bool:
        text = message.lower()
        return any(
            marker in text
            for marker in ("model not exist", "model_not_found", "model not found",
                           "does not exist", "invalid model", "模型不存在", "invalid_parameter.model")
        )

    @staticmethod
    def _extract_image_urls(output: dict) -> list[str]:
        """兼容 choices[].message.content[].image 与 results[].url 两种返回结构。"""
        urls: list[str] = []
        for choice in output.get("choices") or []:
            message = choice.get("message") or {}
            for item in message.get("content") or []:
                if isinstance(item, dict) and item.get("image"):
                    urls.append(item["image"])
        for item in output.get("results") or []:
            if isinstance(item, dict) and item.get("url"):
                urls.append(item["url"])
        return urls

    def _post_sync(self, payload: dict) -> dict:
        """同步提交图像编辑请求，返回 output 字段。"""
        req = urllib.request.Request(
            self._edit_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(
                f"百炼图像编辑失败 HTTP {exc.code}：{self._hint(body, exc.code)} {body[:300]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"百炼图像编辑网络错误：{exc}") from exc

        if result.get("code"):
            raise ProviderError(
                f"百炼图像编辑失败：{result.get('message', result)}；{self._hint(str(result))}"
            )
        output = result.get("output")
        if not isinstance(output, dict):
            raise ProviderError(f"百炼图像编辑响应缺少 output：{json.dumps(result)[:500]}")
        return output

    # ── AI 试衣 ───────────────────────────────────────────
    def try_on(
        self,
        person_image: str,
        top_garment: str | None = None,
        bottom_garment: str | None = None,
        model: str | None = None,
        restore_face: bool = True,
    ) -> str:
        """提交试衣任务并返回结果图片 URL。top/bottom 至少提供一个。"""
        self._check()
        if not top_garment and not bottom_garment:
            raise ProviderError("试衣至少需要上装或下装其中一张图")

        payload_input = {"person_image_url": _image_input(person_image)}
        if top_garment:
            payload_input["top_garment_url"] = _image_input(top_garment)
        if bottom_garment:
            payload_input["bottom_garment_url"] = _image_input(bottom_garment)

        task_id = self._submit(
            {
                "model": model or self.settings.tryon_model,
                "input": payload_input,
                "parameters": {"resolution": -1, "restore_face": restore_face},
            }
        )
        output = self._poll(task_id)
        url = output.get("image_url")
        if not url:
            raise ProviderError(f"试衣任务成功但未返回 image_url：{output}")
        return url

    def parse_garment(self, person_image: str, parse_type: str = "upper") -> dict:
        """调用 aitryon-parsing 分割人物服装，返回 parsing_img_url 与 bbox。"""
        self._check()
        task_id = self._submit(
            {
                "model": "aitryon-parsing",
                "input": {"person_image_url": _image_input(person_image)},
                "parameters": {"parse_type": [parse_type]},
            }
        )
        output = self._poll(task_id)
        results = output.get("results") or []
        first = results[0] if results else output
        return {
            "parsing_img_url": first.get("parsing_img_url") or output.get("parsing_img_url"),
            "bbox": first.get("bbox") or output.get("bbox"),
            "parse_type": parse_type,
            "raw": output,
        }

    # ── 图生视频（万相）────────────────────────────────────
    def generate_video(
        self,
        image: str,
        prompt: str,
        model: str | None = None,
        resolution: str = "480P",
        duration: int = 5,
        negative_prompt: str = "",
        prompt_extend: bool = True,
        watermark: bool = False,
        timeout: int = 600,
    ) -> str:
        """万相图生视频：提交异步任务 -> 轮询 -> 返回视频 URL。"""
        self._check()
        if resolution not in {"480P", "720P", "1080P"}:
            raise ProviderError("分辨率需为 480P / 720P / 1080P")
        if int(duration) not in {5, 10}:
            raise ProviderError("视频时长仅支持 5 秒或 10 秒")

        payload_input = {
            "prompt": prompt.strip()[:2000],
            "img_url": _image_input(image),
        }
        if negative_prompt.strip():
            payload_input["negative_prompt"] = negative_prompt.strip()[:500]

        task_id = self._submit(
            {
                "model": model or self.settings.video_model,
                "input": payload_input,
                "parameters": {
                    "resolution": resolution,
                    "duration": int(duration),
                    "prompt_extend": bool(prompt_extend),
                    "watermark": bool(watermark),
                    "audio": False,
                },
            },
            url=self._video_submit_url,
        )
        output = self._poll(task_id, timeout=timeout)

        video_url = output.get("video_url")
        if not video_url:
            results = output.get("results") or []
            if results and isinstance(results[0], dict):
                video_url = results[0].get("video_url") or results[0].get("url")
        if not video_url:
            raise ProviderError(f"视频任务成功但未返回 video_url：{json.dumps(output)[:500]}")
        return video_url

    # ── DashScope 异步任务 ────────────────────────────────
    def _submit(self, payload: dict, url: str | None = None) -> str:
        req = urllib.request.Request(
            url or self._submit_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.dashscope_api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(f"百炼提交失败 HTTP {exc.code}：{self._hint(body, exc.code)} {body[:300]}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"百炼网络错误：{exc}") from exc

        if result.get("code"):
            raise ProviderError(
                f"百炼提交失败：{result.get('message', result)}；{self._hint(str(result))}"
            )
        try:
            return result["output"]["task_id"]
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"百炼响应缺少 task_id：{result}") from exc

    def _poll(self, task_id: str, timeout: int = 180) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            req = urllib.request.Request(
                self._task_url.format(task_id=task_id),
                headers={"Authorization": f"Bearer {self.settings.dashscope_api_key}"},
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise ProviderError(f"百炼轮询失败 HTTP {exc.code}：{body[:300]}") from exc
            except urllib.error.URLError as exc:
                raise ProviderError(f"百炼轮询网络错误：{exc}") from exc

            output = data.get("output", {})
            status = output.get("task_status")
            if status == "SUCCEEDED":
                return output
            if status == "FAILED":
                message = output.get("message", str(output))
                raise ProviderError(f"百炼任务失败：{message}；{self._hint(message)}")
        raise ProviderError(f"百炼任务超时（{timeout}s），task_id={task_id}")

    @staticmethod
    def _hint(message: str, http_code: int | None = None) -> str:
        text = message.lower()
        if "invalid" in text and "model" in text:
            return "检查模型 ID 及是否已在百炼控制台开通。"
        if "authentication" in text or "unauthorized" in text or http_code == 401:
            return "Key 无效或过期，请到百炼控制台重新生成。"
        if "quota" in text or "insufficient" in text or "balance" in text:
            return "额度不足，请充值后重试。"
        if "region" in text:
            return "AI 试衣仅支持百炼「中国内地（北京）」地域。"
        if "image" in text and ("format" in text or "url" in text):
            return "图片需为 JPG/PNG，且可公网访问或为合法 base64。"
        if http_code == 429:
            return "请求过于频繁，稍后重试。"
        return "请查看百炼控制台任务详情。"
