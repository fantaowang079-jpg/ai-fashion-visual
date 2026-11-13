"""成本台账测试：单价估算、JSONL 追加与汇总。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.cost import (
    CostLedger,
    estimate_cost,
    estimate_video_cost,
    load_prices,
)


class CostTest(unittest.TestCase):
    def test_default_prices_include_edit_models(self):
        prices = load_prices()
        self.assertIn("qwen-image-3.0", prices)
        self.assertGreater(prices["qwen-image-3.0"], 0)

    def test_estimate_cost(self):
        self.assertEqual(estimate_cost("qwen-image-3.0", 1, {"qwen-image-3.0": 0.5}), 0.5)
        self.assertEqual(estimate_cost("qwen-image-3.0", 3, {"qwen-image-3.0": 0.5}), 1.5)
        self.assertIsNone(estimate_cost("unknown-model", 1, {"qwen-image-3.0": 0.5}))
        self.assertIsNone(estimate_cost(None, 1, {"qwen-image-3.0": 0.5}))

    def test_ledger_append_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = CostLedger(Path(tmp) / "ledger.jsonl")
            ledger.record(task_id="t1", status="succeeded", model="qwen-image-3.0",
                          images=2, unit_price=0.5, amount=1.0)
            ledger.record(task_id="t2", status="failed", model="qwen-image-3.0",
                          images=0, unit_price=None, amount=0.0)

            summary = ledger.summary()
            self.assertEqual(summary["calls"], 2)
            self.assertEqual(summary["total_images"], 2)
            self.assertEqual(summary["total_amount"], 1.0)
            self.assertEqual(summary["by_model"]["qwen-image-3.0"]["calls"], 2)
            self.assertEqual(len(summary["recent"]), 2)
            self.assertEqual(summary["recent"][0]["task_id"], "t2")

    def test_video_estimate(self):
        self.assertEqual(
            estimate_video_cost("480P", 5, {"480P": 0.3}), 1.5
        )
        self.assertEqual(
            estimate_video_cost("720P", 10, {"720P": 0.6}), 6.0
        )
        self.assertIsNone(estimate_video_cost("4K", 5, {"480P": 0.3}))

    def test_ledger_empty_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = CostLedger(Path(tmp) / "missing.jsonl").summary()
            self.assertEqual(summary["calls"], 0)
            self.assertEqual(summary["total_amount"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
