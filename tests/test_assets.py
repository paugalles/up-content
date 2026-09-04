import tempfile
import unittest
from pathlib import Path

from scripts.common import assets
from scripts.common.articles import Article
from scripts.common.content import generate


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.directory = Path(self.temp.name)
        article = Article("Guide", "en", "https://x/blog/a", "https://x/blog/a", "Useful source sentence. " * 50, self.directory / "article.md")
        self.content = generate(article, True)

    def tearDown(self): self.temp.cleanup()

    def test_instagram_jpegs_validate(self):
        paths = assets.images(self.content, self.directory)
        assets.validate("instagram", paths)
        self.assertGreaterEqual(len(paths), 5)

    def test_linkedin_pdf_validates(self):
        assets.validate("linkedin", [assets.pdf(self.content, self.directory)])

    @unittest.skipUnless(assets.ffmpeg_executable(), "ffmpeg not installed")
    def test_vertical_video_has_required_streams(self):
        path = assets.video(self.content, self.directory, True)
        assets.validate("youtube", [path])
