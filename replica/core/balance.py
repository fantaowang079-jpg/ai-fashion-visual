"""阿里云账户余额查询（BSS OpenAPI QueryAccountBalance）。

说明：百炼 `sk-` API Key 没有余额接口；真实余额查询需要阿里云 AccessKey。
本模块使用标准库实现 RPC HMAC-SHA1 签名，不引入额外 SDK。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from config import Settings

API_VERSION = "2017-12-14"


def _percent(value) -> str:
    return quote(str(value), safe="~")


def _signature(params: dict, secret: str) -> str:
    canonical = "&".join(
        f"{_percent(key)}={_percent(params[key])}" for key in sorted(params)
    )
    string_to_sign = "GET&%2F&" + _percent(canonical)
    digest = hmac.new(
        f"{secret}&".encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def build_signed_url(settings: Settings) -> str:
    params = {
        "AccessKeyId": settings.aliyun_access_key_id,
        "Action": "QueryAccountBalance",
        "Format": "JSON",
        "RegionId": "cn-hangzhou",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": API_VERSION,
    }
    params["Signature"] = _signature(params, settings.aliyun_access_key_secret)
    query = "&".join(
        f"{_percent(key)}={_percent(params[key])}" for key in sorted(params)
    )
    return f"{settings.bss_endpoint.rstrip('/')}/?{query}"


def _hint(code: str, message: str) -> str:
    text = f"{code} {message}".lower()
    if "invalidaccesskeyid" in text:
        return "AccessKeyId 不存在，检查 RAM 用户 AccessKey。"
    if "signaturedoesnotmatch" in text:
        return "签名不匹配：检查 AccessKeySecret，或本机时间与标准时间偏差是否超过 15 分钟。"
    if "nopermission" in text or "notauthorized" in text or "forbidden" in text:
        return "当前 RAM 用户没有余额查询权限，请授予 AliyunBSSReadOnlyAccess。"
    if "throttling" in text:
        return "请求过于频繁，稍后重试。"
    return "请检查阿里云 AccessKey 与 RAM 权限。"


def query_account_balance(settings: Settings) -> dict:
    if not settings.aliyun_access_key_id or not settings.aliyun_access_key_secret:
        return {
            "available": False,
            "configured": False,
            "message": (
                "未配置阿里云 AccessKey，无法查询账户余额。"
                "百炼 sk- API Key 没有余额接口；请在 .env 配置 "
                "ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET。"
            ),
        }

    url = build_signed_url(settings)
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"Code": f"HTTP {exc.code}", "Message": body[:300]}
        code = str(payload.get("Code") or "")
        message = str(payload.get("Message") or body[:300])
        return {
            "available": False,
            "configured": True,
            "error": f"{code}: {message}".strip(": "),
            "hint": _hint(code, message),
        }
    except urllib.error.URLError as exc:
        return {
            "available": False,
            "configured": True,
            "error": f"网络错误：{exc}",
            "hint": "检查网络/代理，或 BSS_ENDPOINT 是否可访问。",
        }
    except Exception as exc:
        return {
            "available": False,
            "configured": True,
            "error": f"查询失败：{exc}",
        }

    if data.get("Code") or data.get("Success") is False:
        code = str(data.get("Code") or "")
        message = str(data.get("Message") or "")
        return {
            "available": False,
            "configured": True,
            "error": f"{code}: {message}".strip(": "),
            "hint": _hint(code, message),
        }

    payload = data.get("Data") or {}
    return {
        "available": True,
        "configured": True,
        "currency": payload.get("Currency", "CNY"),
        "available_amount": payload.get("AvailableAmount"),
        "cash_amount": payload.get("AvailableCashAmount"),
        "credit_amount": payload.get("CreditAmount"),
        "mybank_credit_amount": payload.get("MybankCreditAmount"),
        "checked_at": time.time(),
    }
