import logging
import json
import shutil
import tempfile
from pathlib import Path

from . import assets, publishers
from .articles import fetch_article, load_article
from .config import truthy
from .content import generate


def _execute(platform: str, directory: Path, dry: bool, generate_only: bool, article_path: Path | None) -> int:
    article = load_article(article_path) if article_path else fetch_article(directory)
    logging.info("Selected %s article: %s", article.language, article.canonical_url)
    content = generate(article, dry)
    caption = (content["caption"] + "\n\n" + " ".join(content["hashtags"])).strip()
    if platform == "instagram":
        from .layouts.instagram import generate_instagram_images
        generated = generate_instagram_images(content, directory)
    elif platform == "facebook":
        from .layouts.facebook import generate_facebook_card
        output = directory / "facebook.jpg"
        generate_facebook_card(content["slides"][0], output, (1200, 1500))
        generated = [output]
    elif platform == "linkedin":
        from .generators import NarrationGenerator
        from .layouts.linkedin import LinkedinSlideGenerator
        scenes = NarrationGenerator().generate_scenes(article)
        output = directory / "presentation.pptx"
        sg = LinkedinSlideGenerator({"video": {"resolution": (1920, 1080)}})
        sg.generate_pptx(scenes, str(output))
        generated = [output]
    elif platform == "youtube":
        from .generators import NarrationGenerator, EdgeTTSProvider, VideoComposer
        from .layouts.youtube import YoutubeSlideGenerator
        import asyncio, os
        scenes = NarrationGenerator().generate_scenes(article)
        audio_path = str(directory / "narration.mp3")
        if not dry:
            asyncio.run(EdgeTTSProvider({"language": article.language}).generate(" ".join(s.spoken_text for s in scenes), audio_path))
        else:
            Path(audio_path).write_bytes(b"") # mock audio
        slides_dir = directory / "slides"
        slides_dir.mkdir(exist_ok=True)
        sg = YoutubeSlideGenerator({"video": {"resolution": (1920, 1080)}})
        for i, scene in enumerate(scenes):
            sg.generate_image(scene, str(slides_dir / f"slide_{i}.png"))
        output_path = directory / "youtube.mp4"
        if not dry:
            vc = VideoComposer({"video": {"resolution": (1920, 1080), "fps": 24}, "branding": {"logo_path": "scripts/assets/brand/inmibot-logo-white.png"}, "music": {"folder": "scripts/assets/music", "volume": 0.1, "fade_duration": 2}})
            vc.compose(audio_path, str(slides_dir), scenes, str(output_path))
        else:
            output_path.write_bytes(b"")
        generated = [output_path]
    elif platform == "tiktok":
        from .layouts.tiktok import create_tiktok_poster
        slides_dir = directory / "slides"
        slides_dir.mkdir(exist_ok=True)
        slides = content.get("slides", [])
        frames = []
        for i, slide in enumerate(slides):
            p = slides_dir / f"slide_{i}.jpg"
            if not dry:
                create_tiktok_poster(slide["title"], slide["body"], f"PASO {i+1}", str(p), is_centered=(i==0))
            else:
                p.write_bytes(b"")
            frames.append(p)
        generated = frames

    assets.validate(platform, generated)
    metadata = {"platform": platform, "article": {"title": article.title, "language": article.language, "url": article.canonical_url}, "content": content, "caption": caption, "assets": [path.name for path in generated]}
    (directory / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if article_path and article_path.resolve() != (directory / "article.md").resolve():
        shutil.copy2(article_path, directory / "article.md")
    logging.info("Generated and validated %s assets in %s", platform, directory)
    if generate_only or dry:
        logging.info("Publication skipped (%s)", "--generate-only" if generate_only else "DRY_RUN")
        return 0
    if platform == "instagram": publication_id = publishers.instagram(generated, caption)
    elif platform == "facebook": publication_id = publishers.facebook(generated[0], caption)
    elif platform == "linkedin": publication_id = publishers.linkedin(generated[0], caption)
    elif platform == "tiktok": publication_id = publishers.tiktok(generated, caption)
    else: publication_id = publishers.youtube(generated[0], content)
    logging.info("Published %s ID: %s", platform, publication_id)
    return 0


def run(platform: str, *, generate_only: bool = False, output_dir: Path | None = None, article_path: Path | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dry = truthy("DRY_RUN")
    if output_dir and not generate_only:
        raise RuntimeError("--output-dir requires --generate-only")
    if generate_only:
        directory = (output_dir or Path("generated") / platform).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return _execute(platform, directory, dry, True, article_path)
    with tempfile.TemporaryDirectory(prefix=f"inmibot-{platform}-") as temp:
        return _execute(platform, Path(temp), dry, False, article_path)
