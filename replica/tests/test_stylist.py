"""智能穿搭测试：衣橱数据、规则兜底与 Prompt 约束。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.stylist import (
    WARDROBE_PATH,
    build_prompt,
    fallback_schemes,
    load_wardrobe,
)


class WardrobeTest(unittest.TestCase):
    def test_wardrobe_loaded(self):
        items = load_wardrobe()
        self.assertGreaterEqual(len(items), 20)
        ids = [item["id"] for item in items]
        self.assertEqual(len(ids), len(set(ids)))

    def test_fallback_returns_three_valid_schemes(self):
        wardrobe = load_wardrobe()
        valid_ids = {item["id"] for item in wardrobe}
        result = fallback_schemes("通勤", "四季", "中性", "米色针织开衫")
        schemes = result["schemes"]
        self.assertEqual(len(schemes), 3)
        for scheme in schemes:
            self.assertTrue(scheme["title"])
            self.assertGreaterEqual(len(scheme["items"]), 3)
            self.assertTrue(set(scheme["item_ids"]).issubset(valid_ids))
            self.assertIn("通勤", scheme["reason"])
            self.assertTrue(scheme["instruction"])
            self.assertEqual(scheme["anchor"], "米色针织开衫")

    def test_prompt_only_allows_wardrobe_ids(self):
        wardrobe = load_wardrobe()
        prompt = build_prompt(wardrobe, "约会", "春夏", "暖色", "碎花茶歇裙")
        self.assertIn("禁止编造", prompt)
        self.assertIn("W01", prompt)
        self.assertIn("只输出 JSON", prompt)
        self.assertIn("碎花茶歇裙", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
