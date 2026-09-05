import os
os.environ.setdefault("ARTICLE_BASE_URL", "https://example.com")
os.environ.setdefault("BRAND_NAME", "TestBrand")
os.environ.setdefault("BRAND_SITE", "testbrand.com")
os.environ.setdefault("BRAND_CTA_ES", "CTA ES")
os.environ.setdefault("BRAND_CTA_EN", "CTA EN")

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.common.cli import main


ARTICLE = """---
title: "Repeatable public guide"
language: en
url: "https://example.test/blog/guide"
---

# Repeatable public guide

This public source explains useful immigration information for readers. It describes the topic carefully without adding unsupported requirements. The complete article provides context that can be summarized for educational social content.

Readers should review the current official requirements and obtain individual professional advice where appropriate. This material is general information and does not promise an outcome.
"""


class CliTests(unittest.TestCase):
    def test_all_platforms_support_generation_contract(self):
        for platform in ("youtube", "instagram", "facebook", "tiktok", "linkedin", "linkedin_and_youtube", "instagram_and_tiktok"):
            with self.subTest(platform=platform), patch("scripts.common.cli.run", return_value=0) as execute:
                result = main(platform, ["--generate-only", "--output-dir", f"generated/{platform}", "--article", "article.md"])
                self.assertEqual(result, 0)
                kwargs = execute.call_args.kwargs
                self.assertTrue(kwargs["generate_only"])
                self.assertEqual(kwargs["output_dir"], Path(f"generated/{platform}"))
                self.assertEqual(kwargs["article_path"], Path("article.md"))

    def test_generate_only_local_article_persists_assets_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            article = root / "source.md"; article.write_text(ARTICLE, encoding="utf-8")
            output = root / "generated" / "instagram"
            with patch.dict("os.environ", {"DRY_RUN": "true", "BRAND_NAME": "TestBrand", "BRAND_SITE": "testbrand.com", "BRAND_CTA_ES": "CTA ES", "BRAND_CTA_EN": "CTA EN"}, clear=True), patch("scripts.common.pipeline.publishers.instagram") as publish:
                self.assertEqual(main("instagram", ["--generate-only", "--output-dir", str(output), "--article", str(article)]), 0)
            publish.assert_not_called()
            metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["article"]["url"], "https://example.test/blog/guide")
            self.assertTrue((output / "article.md").is_file())
            self.assertGreaterEqual(len(list(output.glob("slide-*.jpg"))), 5)

    def test_output_directory_requires_generate_only(self):
        with self.assertRaises(SystemExit):
            main("facebook", ["--output-dir", "generated/facebook"])
