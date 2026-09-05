import os
os.environ.setdefault("ARTICLE_BASE_URL", "https://example.com")
os.environ.setdefault("BRAND_NAME", "TestBrand")
os.environ.setdefault("BRAND_SITE", "testbrand.com")
os.environ.setdefault("BRAND_CTA_ES", "CTA ES")
os.environ.setdefault("BRAND_CTA_EN", "CTA EN")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.common import publishers
from scripts.common.articles import Article
from scripts.common.content import generate
from scripts.common.config import require
from scripts.common.http import Http


class BoundaryTests(unittest.TestCase):
    def test_openai_structured_json_boundary(self):
        response = Mock(output_text='{"title":"Guide","caption":"Read it. Not legal advice.","hashtags":["#one","#two","#three","#four"],"slides":[' + ','.join(['{"label":"1","title":"Point","body":"Source fact"}'] * 5) + '],"narration":"Source fact. Not legal advice."}')
        client = Mock(); client.responses.create.return_value = response
        article = Article("Guide", "en", "https://x/blog/a", "https://x/blog/a", "Source fact. " * 30, Path("unused"))
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test", "BRAND_NAME": "TestBrand", "BRAND_SITE": "testbrand.com", "BRAND_CTA_ES": "CTA ES", "BRAND_CTA_EN": "CTA EN"}, clear=True), patch("openai.OpenAI", return_value=client):
            result = generate(article, False)
        self.assertEqual(len(result["slides"]), 5)
        self.assertEqual(client.responses.create.call_args.kwargs["text"]["format"]["type"], "json_schema")

    def test_missing_env_is_actionable(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(RuntimeError, "EXAMPLE_TOKEN"):
            require("EXAMPLE_TOKEN")

    def test_http_retries_transient_status(self):
        bad = Mock(status_code=503); bad.raise_for_status.side_effect = __import__("requests").HTTPError()
        good = Mock(status_code=200); good.raise_for_status.return_value = None
        session = Mock(); session.request.side_effect = [bad, good]
        with patch("scripts.common.http.time.sleep"):
            self.assertIs(Http(session, attempts=2).request("GET", "https://example.test"), good)

    def test_facebook_uses_graph_photo_api(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "a.jpg"; image.write_bytes(b"jpeg")
            http = Mock()
            http.json.side_effect = [{"files": [{"url": "http://tmp/image.jpg"}]}, {"id": "media-1"}, {"id": "post-1"}]
            env = {"FACEBOOK_PAGE_ACCESS_TOKEN": "token"}
            with patch.dict("os.environ", env, clear=True):
                self.assertEqual(publishers.facebook([image], "copy", http), "post-1")
            self.assertIn("/me/feed", http.json.call_args.args[1])

    def test_tiktok_validates_creator_privacy_before_init(self):
        http = Mock(); http.json.return_value = {"data": {"privacy_level_options": ["SELF_ONLY"]}}
        with tempfile.TemporaryDirectory() as temp, patch.dict("os.environ", {"TIKTOK_ACCESS_TOKEN": "x", "TIKTOK_PRIVACY_LEVEL": "PUBLIC_TO_EVERYONE"}, clear=True):
            video = Path(temp) / "v.mp4"; video.write_bytes(b"x")
            with self.assertRaisesRegex(RuntimeError, "not available"), patch("scripts.common.publishers.subprocess.run") as probe:
                publishers.tiktok(video, "copy", http)
            self.assertEqual(http.json.call_count, 1)
            probe.assert_not_called()
