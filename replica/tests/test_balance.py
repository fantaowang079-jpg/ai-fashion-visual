"""余额查询测试：URL 编码、签名构造与未配置提示。"""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import get_settings
from core.balance import _percent, build_signed_url, query_account_balance


class BalanceTest(unittest.TestCase):
    def test_percent_encoding(self):
        self.assertEqual(_percent("a b/中文~"), "a%20b%2F%E4%B8%AD%E6%96%87~")

    def test_signed_url_contains_required_params(self):
        settings = replace(
            get_settings(),
            aliyun_access_key_id="LTAI_TEST_ID",
            aliyun_access_key_secret="secret_value",
            bss_endpoint="https://business.aliyuncs.com",
        )
        url = build_signed_url(settings)
        self.assertIn("Action=QueryAccountBalance", url)
        self.assertIn("Version=2017-12-14", url)
        self.assertIn("AccessKeyId=LTAI_TEST_ID", url)
        self.assertIn("Signature=", url)
        self.assertNotIn("secret_value", url)

    def test_unconfigured_returns_guidance(self):
        settings = replace(
            get_settings(),
            aliyun_access_key_id="",
            aliyun_access_key_secret="",
        )
        result = query_account_balance(settings)
        self.assertFalse(result["available"])
        self.assertFalse(result["configured"])
        self.assertIn("AccessKey", result["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
