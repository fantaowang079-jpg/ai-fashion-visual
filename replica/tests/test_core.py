"""复刻版核心逻辑测试：不依赖网络与 API Key。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import _derive_native_base, get_settings, looks_like_aliyun_access_key
from core.model_library import load_models, recommend_model
from core.pipeline import run_angles, run_restyle, run_tryon, run_video
from core.prompts import (
    RESTYLE_GUARD,
    build_angle_prompt,
    build_restyle_prompt,
    build_tryon_edit_prompt,
    build_tryon_prompt,
)
from core.session import Session


class CredentialTest(unittest.TestCase):
    def test_access_key_is_detected(self):
        self.assertTrue(looks_like_aliyun_access_key("LTAI5tExample"))
        self.assertFalse(looks_like_aliyun_access_key("sk-abcdef123456"))
        self.assertFalse(looks_like_aliyun_access_key(""))

    def test_workspace_native_base_derivation(self):
        base = "https://ws123.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        self.assertEqual(
            _derive_native_base(base),
            "https://ws123.cn-beijing.maas.aliyuncs.com/api/v1",
        )


class ModelLibraryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()
        cls.models = load_models(cls.settings.model_lib)

    def test_library_has_models(self):
        self.assertEqual(len(self.models), 45)

    def test_recommend_jk_is_female(self):
        picked = recommend_model(self.models, "JK制服 百褶裙")
        self.assertEqual(picked["gender"], "female")
        self.assertEqual(picked["ageGroup"], "adult")

    def test_recommend_menswear_is_male(self):
        picked = recommend_model(self.models, "男装西装")
        self.assertEqual(picked["gender"], "male")

    def test_recommend_children(self):
        picked = recommend_model(self.models, "童装 连衣裙")
        self.assertEqual(picked["ageGroup"], "child")


class PromptTest(unittest.TestCase):
    def test_top_lock_mentions_upper_body(self):
        prompt = build_tryon_prompt("白色T恤", "top")
        self.assertIn("TOP garment", prompt)
        self.assertIn("full body", prompt)

    def test_prompt_reference_order_matches_inputs(self):
        # pipeline 的参考图顺序是 [模特, 服装]，prompt 必须一致
        prompt = build_tryon_prompt("白色T恤", "top")
        self.assertIn("参考图1（模特）和参考图2（服装）", prompt)

    def test_one_piece_lock(self):
        prompt = build_tryon_prompt("黑色连衣裙", "one_piece")
        self.assertIn("ONE-PIECE", prompt)

    def test_angle_prompt_contains_suffix(self):
        prompt = build_angle_prompt("bottom", "back view, full body", "牛仔裙")
        self.assertIn("back view", prompt)
        self.assertIn("EXACT bottom garment", prompt)


class RestylePromptTest(unittest.TestCase):
    def test_instruction_prompt_contains_guard(self):
        prompt = build_restyle_prompt("换成米色针织开衫")
        self.assertIn("换成米色针织开衫", prompt)
        self.assertIn(RESTYLE_GUARD, prompt)
        self.assertIn("图1", prompt)

    def test_garment_reference_prompt(self):
        prompt = build_restyle_prompt(
            "", part="one_piece", has_garment_reference=True
        )
        self.assertIn("图2是目标连衣裙或连体装", prompt)
        self.assertIn("自然垂合", prompt)
        self.assertIn(RESTYLE_GUARD, prompt)

    def test_instruction_required_without_garment(self):
        with self.assertRaises(ValueError):
            build_restyle_prompt("")

    def test_tryon_edit_prompt(self):
        top = build_tryon_edit_prompt("top", desc="白色棉质衬衫")
        self.assertIn("图2是目标上装", top)
        self.assertIn("服装参考描述：白色棉质衬衫", top)
        self.assertIn(RESTYLE_GUARD, top)

        full = build_tryon_edit_prompt("full")
        self.assertIn("图2是上装", full)
        self.assertIn("图3是下装", full)


class SessionTest(unittest.TestCase):
    def test_stage_dirs_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Session(Path(tmp), fresh=True)
            tryon_dir = session.stage_dir("tryon")
            self.assertTrue(tryon_dir.exists())
            session.log_generation(action="test", note="hello")
            self.assertTrue(session.log_path.exists())
            content = session.log_path.read_text(encoding="utf-8")
            self.assertIn('"action": "test"', content)


class DryRunPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()

    def test_dry_run_tryon_with_desc(self):
        plan, records = run_tryon(
            settings=self.settings,
            desc="白色宽松短袖T恤",
            part="top",
            dry_run=True,
        )
        self.assertEqual(records, [])
        self.assertIn(plan.method, {"seedream", "qwen"})
        if self.settings.tryon_engine == "edit":
            self.assertEqual(plan.details["engine"], "edit")
            self.assertIn("图2是目标上装", plan.prompt)
        else:
            self.assertIn("full body", plan.prompt)
        self.assertTrue(plan.references)

    def test_dry_run_tryon_with_refs(self):
        plan, records = run_tryon(
            settings=self.settings,
            garment="garment.jpg",
            model="model.jpg",
            part="one_piece",
            method="qwen",
            dry_run=True,
        )
        self.assertEqual(records, [])
        self.assertEqual(plan.method, "qwen")
        self.assertEqual(plan.references, ["model.jpg", "garment.jpg"])

    def test_full_requires_bottom(self):
        with self.assertRaises(ValueError):
            run_tryon(settings=self.settings, garment="g.jpg", part="full", dry_run=True)

    def test_invalid_variants(self):
        with self.assertRaises(ValueError):
            run_tryon(settings=self.settings, garment="g.jpg", variants=9, dry_run=True)

    def test_dry_run_restyle_instructions(self):
        plans, records = run_restyle(
            settings=self.settings,
            image="https://example.com/person.jpg",
            instructions=["换成米色针织开衫", "加一件同色系外套"],
            dry_run=True,
        )
        self.assertEqual(records, [])
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0].action, "restyle")
        self.assertEqual(plans[0].method, "qwen-image-edit")
        self.assertIn("米色针织开衫", plans[0].prompt)
        self.assertEqual(plans[0].references, ["https://example.com/person.jpg"])

    def test_dry_run_restyle_with_garment(self):
        plans, _ = run_restyle(
            settings=self.settings,
            image="https://example.com/person.jpg",
            garment="https://example.com/garment.jpg",
            part="one_piece",
            count=2,
            dry_run=True,
        )
        self.assertEqual(len(plans), 1)
        self.assertEqual(
            plans[0].references,
            ["https://example.com/person.jpg", "https://example.com/garment.jpg"],
        )
        self.assertIn("图2", plans[0].prompt)
        self.assertEqual(plans[0].details["count"], 2)

    def test_restyle_requires_instruction_or_garment(self):
        with self.assertRaises(ValueError):
            run_restyle(
                settings=self.settings,
                image="https://example.com/person.jpg",
                dry_run=True,
            )

    def test_restyle_rejects_bad_count_and_size(self):
        with self.assertRaises(ValueError):
            run_restyle(
                settings=self.settings,
                image="https://example.com/person.jpg",
                instructions=["换成米色"],
                count=9,
                dry_run=True,
            )
        with self.assertRaises(ValueError):
            run_restyle(
                settings=self.settings,
                image="https://example.com/person.jpg",
                instructions=["换成米色"],
                size="100*100",
                dry_run=True,
            )

    def test_dry_run_angles(self):
        plans, records = run_angles(
            settings=self.settings,
            garment="g.jpg",
            model="m.jpg",
            preset="ecommerce,detail",
            part="top",
            dry_run=True,
        )
        self.assertEqual(records, [])
        self.assertEqual(len(plans), 6)
        self.assertIn("front view", plans[0].prompt)

    def test_dry_run_video_single_and_multi(self):
        plan, records = run_video(settings=self.settings, image="a.jpg", dry_run=True)
        self.assertEqual(records, [])
        self.assertEqual(plan.action, "video")
        if self.settings.dashscope_api_key:
            self.assertEqual(plan.method, "wan-i2v")
            self.assertEqual(plan.details["model"], self.settings.video_model)
            self.assertIn("全身", plan.prompt)
        else:
            self.assertIn("full body always visible", plan.prompt)

        plan2, _ = run_video(
            settings=self.settings,
            images=["a.jpg", "b.jpg"],
            dry_run=True,
        )
        self.assertEqual(plan2.details["model"], self.settings.ark_video_model_lite)

    def test_video_rejects_too_many_refs(self):
        with self.assertRaises(ValueError):
            run_video(settings=self.settings, images=["1.jpg", "2.jpg", "3.jpg", "4.jpg", "5.jpg"], dry_run=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
