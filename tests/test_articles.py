import os
os.environ.setdefault("ARTICLE_BASE_URL", "https://example.com")
os.environ.setdefault("BRAND_NAME", "TestBrand")
os.environ.setdefault("BRAND_SITE", "testbrand.com")
os.environ.setdefault("BRAND_CTA_ES", "CTA ES")
os.environ.setdefault("BRAND_CTA_EN", "CTA EN")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from scripts.common.articles import discover_urls, fetch_article


class ArticleTests(unittest.TestCase):
    def test_language_specific_discovery(self):
        response = Mock(content=b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/blog/es-post</loc></url><url><loc>https://example.com/en/blog/en-post</loc></url></urlset>')
        http = Mock(); http.request.return_value = response
        self.assertEqual(discover_urls("https://example.test/sitemap.xml", "en", http), ["https://example.com/en/blog/en-post", "https://example.com/en/blog/es-post"])
        self.assertEqual(discover_urls("https://example.test/sitemap.xml", "es", http), ["https://example.com/blog/es-post", "https://example.com/es/blog/en-post"])

    def test_language_is_chosen_before_article(self):
        sitemap = Mock(content=b'<urlset><url><loc>https://example.com/en/blog/published</loc></url></urlset>')
        article = Mock(text='<html><head><link rel="canonical" href="/en/blog/canonical"></head><body><article><h1>A useful guide</h1><p>' + ('Grounded source information. ' * 20) + '</p></article></body></html>')
        http = Mock(); http.request.side_effect = [sitemap, article]
        choices = iter(["en", "https://example.com/en/blog/published"])
        with tempfile.TemporaryDirectory() as temp:
            result = fetch_article(Path(temp), http=http, chooser=lambda _: next(choices))
            self.assertEqual(result.language, "en")
            self.assertEqual(result.canonical_url, "https://example.com/en/blog/canonical")
            self.assertTrue(result.markdown_path.exists())

    def test_no_articles_is_a_failure(self):
        http = Mock(); http.request.return_value = Mock(content=b"<urlset />")
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(RuntimeError, "No published es"):
            fetch_article(Path(temp), http=http, chooser=lambda _: "es")

    def test_empty_workflow_sitemap_variable_uses_default(self):
        http = Mock(); http.request.return_value = Mock(content=b"<urlset />")
        with tempfile.TemporaryDirectory() as temp, unittest.mock.patch.dict("os.environ", {"ARTICLE_SITEMAP_URL_ES": "", "ARTICLE_BASE_URL": "https://example.com"}, clear=True), self.assertRaises(RuntimeError):
            fetch_article(Path(temp), http=http, chooser=lambda _: "es")
        self.assertEqual(http.request.call_args.args[1], "https://example.com/sitemap.xml")
