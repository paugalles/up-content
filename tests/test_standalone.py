import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.common.articles import Article
from scripts.common.pipeline import run


ROOT = Path(__file__).resolve().parents[1]


class StandaloneTests(unittest.TestCase):
    def test_runtime_and_config_have_no_parent_repository_dependencies(self):
        forbidden = [
            "rag" + "-immigration-spanish",
            ".." + "/rag" + "-immigration-spanish",
            "djan" + "go",
            "DATABASE" + "_URL",
        ]
        files = list((ROOT / "scripts").rglob("*.py"))
        files += list((ROOT / "tests").rglob("*.py"))
        files += list((ROOT / ".github" / "workflows").glob("*.yml"))
        files += [ROOT / "requirements.txt", ROOT / ".env.example"]
        for path in files:
            text = path.read_text(encoding="utf-8").lower()
            for token in forbidden:
                self.assertNotIn(token.lower(), text, f"forbidden standalone dependency in {path}")

    def test_standalone_instagram_dry_run_smoke(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "article.md"
            source.write_text("# Standalone guide\n\n" + "Public source fact. " * 80, encoding="utf-8")
            article = Article(
                "Standalone guide", "en", "https://example.test/blog/guide",
                "https://example.test/blog/guide", "Public source fact. " * 80,
                source,
            )
            with patch.dict("os.environ", {"DRY_RUN": "true"}, clear=True), patch(
                "scripts.common.pipeline.fetch_article", return_value=article
            ), patch("scripts.common.pipeline.publishers.instagram") as publish:
                self.assertEqual(run("instagram"), 0)
            publish.assert_not_called()
