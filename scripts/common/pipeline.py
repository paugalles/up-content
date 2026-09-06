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
            vc = VideoComposer({"video": {"resolution": (1920, 1080), "fps": 24}, "branding": {"logo_path": os.getenv("BRAND_LOGO_PATH") or "scripts/assets/brand/logo.png"}, "music": {"folder": "scripts/assets/music", "volume": 0.2, "fade_duration": 2}})
            vc.compose(audio_path, str(slides_dir), scenes, str(output_path))
        else:
            output_path.write_bytes(b"")
        generated = [output_path]
    elif platform == "linkedin_and_youtube":
        from .generators import NarrationGenerator, EdgeTTSProvider, VideoComposer
        from .layouts.linkedin import LinkedinSlideGenerator
        from .layouts.youtube import YoutubeSlideGenerator
        import asyncio, os
        
        # 1. Generate scenes exactly once
        scenes = NarrationGenerator().generate_scenes(article)
        
        # 2. Generate LinkedIn PPTX
        linkedin_output = directory / "presentation.pptx"
        sg_li = LinkedinSlideGenerator({"video": {"resolution": (1920, 1080)}})
        sg_li.generate_pptx(scenes, str(linkedin_output))
        
        # 3. Generate YouTube MP4
        audio_path = str(directory / "narration.mp3")
        if not dry:
            asyncio.run(EdgeTTSProvider({"language": article.language}).generate(" ".join(s.spoken_text for s in scenes), audio_path))
        else:
            Path(audio_path).write_bytes(b"") # mock audio
            
        slides_dir = directory / "slides"
        slides_dir.mkdir(exist_ok=True)
        sg_yt = YoutubeSlideGenerator({"video": {"resolution": (1920, 1080)}})
        for i, scene in enumerate(scenes):
            sg_yt.generate_image(scene, str(slides_dir / f"slide_{i}.png"))
            
        youtube_output = directory / "youtube.mp4"
        if not dry:
            vc = VideoComposer({"video": {"resolution": (1920, 1080), "fps": 24}, "branding": {"logo_path": os.getenv("BRAND_LOGO_PATH") or "scripts/assets/brand/logo.png"}, "music": {"folder": "scripts/assets/music", "volume": 0.2, "fade_duration": 2}})
            vc.compose(audio_path, str(slides_dir), scenes, str(youtube_output))
        else:
            youtube_output.write_bytes(b"")
            
        generated = [linkedin_output, youtube_output]
    elif platform == "tiktok":
        from .layouts.tiktok import create_tiktok_poster
        slides_dir = directory / "slides"
        slides_dir.mkdir(exist_ok=True)
        slides = content.get("slides", [])
        frames = []
        for i, slide in enumerate(slides):
            p = slides_dir / f"slide_{i}.jpg"
            if not dry:
                create_tiktok_poster(slide["title"], slide["body"], f"PASO {i+1}" if i > 0 and i < len(slides)-1 else "", str(p), is_centered=(i==0), is_last=(i==len(slides)-1))
            else:
                p.write_bytes(b"")
            frames.append(p)
        generated = frames
    elif platform == "instagram_and_tiktok":
        from .layouts.instagram import generate_instagram_images
        from .layouts.tiktok import create_tiktok_poster
        from moviepy.editor import ImageSequenceClip, AudioFileClip, afx
        import os
        
        # 1. Generate Instagram images
        ig_dir = directory / "instagram"
        ig_dir.mkdir(exist_ok=True)
        ig_generated = generate_instagram_images(content, ig_dir)
        
        # 2. Generate Facebook Video (using Instagram slides + music)
        fb_video_path = directory / "facebook.mp4"
        if not dry:
            ig_paths = [str(p) for p in ig_generated]
            clip = ImageSequenceClip(ig_paths, durations=[4]*len(ig_paths))
            audio_path = "scripts/assets/music/corporate.mp3"
            if os.path.exists(audio_path):
                audio = AudioFileClip(audio_path)
                if audio.duration < clip.duration:
                    audio = afx.audio_loop(audio, duration=clip.duration)
                else:
                    audio = audio.subclip(0, clip.duration)
                audio = audio.audio_fadeout(2)
                clip = clip.set_audio(audio)
            clip.write_videofile(str(fb_video_path), fps=24, codec="libx264", audio_codec="aac")
        else:
            fb_video_path.write_bytes(b"")
            
        # 3. Generate TikTok frames
        tk_dir = directory / "tiktok"
        tk_dir.mkdir(exist_ok=True)
        slides = content.get("slides", [])
        tk_generated = []
        for i, slide in enumerate(slides):
            p = tk_dir / f"slide_{i}.jpg"
            if not dry:
                create_tiktok_poster(slide["title"], slide["body"], f"PASO {i+1}" if i > 0 and i < len(slides)-1 else "", str(p), is_centered=(i==0), is_last=(i==len(slides)-1))
            else:
                p.write_bytes(b"")
            tk_generated.append(p)
            
        generated = ig_generated + tk_generated + [fb_video_path]

    if platform == "instagram_and_tiktok":
        assets.validate("instagram", ig_generated)
        assets.validate("tiktok", tk_generated)
        # basic video validation
        assets.validate("youtube", [fb_video_path])
    else:
        assets.validate(platform, generated)
        
    if platform == "instagram_and_tiktok":
        metadata_assets = {
            "instagram": [path.name for path in ig_generated],
            "tiktok": [path.name for path in tk_generated],
            "facebook": [fb_video_path.name]
        }
    else:
        metadata_assets = [path.name for path in generated]
        
    metadata = {"platform": platform, "article": {"title": article.title, "language": article.language, "url": article.canonical_url}, "content": content, "caption": caption, "assets": metadata_assets}
    (directory / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if article_path and article_path.resolve() != (directory / "article.md").resolve():
        shutil.copy2(article_path, directory / "article.md")
    logging.info("Generated and validated %s assets in %s", platform, directory)
    if generate_only or dry:
        logging.info("Publication skipped (%s)", "--generate-only" if generate_only else "DRY_RUN")
        return 0
    if platform == "instagram": 
        # Cross-post to facebook using the same assets and caption FIRST
        fb_publication_id = publishers.facebook(generated, caption)
        logging.info("Published facebook ID: %s", fb_publication_id)
        
        # Then publish to instagram
        publication_id = publishers.instagram(generated, caption)
        logging.info("Published instagram ID: %s", publication_id)
    elif platform == "linkedin": publication_id = publishers.linkedin(generated[0], caption)
    elif platform == "linkedin_and_youtube":
        # li_id = publishers.linkedin(generated[0], caption) # Disabled until credentials are ready
        yt_id = publishers.youtube(generated[1], content)
        # logging.info("Published linkedin ID: %s", li_id)
        logging.info("Published youtube ID: %s", yt_id)
        publication_id = f"LI:skipped, YT:{yt_id}"
    elif platform == "instagram_and_tiktok":
        fb_id = publishers.facebook_video(fb_video_path, caption)
        ig_id = publishers.instagram(ig_generated, caption)
        # tk_id = publishers.tiktok(tk_generated, caption) # Disabled until credentials are ready
        logging.info("Published facebook ID: %s", fb_id)
        logging.info("Published instagram ID: %s", ig_id)
        # logging.info("Published tiktok ID: %s", tk_id)
        publication_id = f"FB:{fb_id}, IG:{ig_id}, TK:skipped"
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
    with tempfile.TemporaryDirectory(prefix=f"social-{platform}-") as temp:
        return _execute(platform, Path(temp), dry, False, article_path)
