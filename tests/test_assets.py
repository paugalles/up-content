import os
os.environ.setdefault("ARTICLE_BASE_URL", "https://example.com")
os.environ.setdefault("BRAND_NAME", "TestBrand")
os.environ.setdefault("BRAND_SITE", "testbrand.com")
os.environ.setdefault("BRAND_CTA_ES", "CTA ES")
os.environ.setdefault("BRAND_CTA_EN", "CTA EN")

import tempfile
import unittest
from pathlib import Path

from scripts.common import assets
from scripts.common.articles import Article
from scripts.common.content import generate
from scripts.common.layouts.instagram import generate_instagram_images
from scripts.common.layouts.linkedin import LinkedinSlideGenerator
from scripts.common.generators import Scene

class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.article = Article("Guide", "en", "https://x/blog/a", "https://x/blog/a", "Useful source sentence. " * 50, self.directory / "article.md")
        self.content = generate(self.article, True)

    def tearDown(self): 
        self.temp.cleanup()

    def test_instagram_jpegs_validate(self):
        paths = generate_instagram_images(self.content, self.directory)
        assets.validate("instagram", paths)
        self.assertGreaterEqual(len(paths), 5)

    def test_linkedin_pdf_validates(self):
        scenes = [Scene(spoken_text="test", slide_title="Title", slide_body="Body", is_title=True)]
        output = self.directory / "presentation.pptx"
        sg = LinkedinSlideGenerator({"video": {"resolution": (1920, 1080)}})
        sg.generate_pptx(scenes, str(output))
        assets.validate("linkedin", [output])

    @unittest.skipUnless(assets.ffmpeg_executable(), "ffmpeg not installed")
    def test_vertical_video_has_required_streams(self):
        import subprocess
        output = self.directory / "video.mp4"
        subprocess.run([
            assets.ffmpeg_executable(), "-y", 
            "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=24", 
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "1", "-c:v", "libx264", "-c:a", "aac", str(output)
        ], check=True, capture_output=True)
        assets.validate("youtube", [output])

