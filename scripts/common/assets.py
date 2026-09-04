import json
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import branding


def ffmpeg_executable() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


def _font(size: int):
    configured = branding().font_path
    for path in (configured, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if not path:
            continue
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(draw, text, font, width):
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and draw.textbbox((0, 0), candidate, font=font)[2] > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        elif not paragraph:
            lines.append("")
    return lines


def card(slide: dict, output: Path, size: tuple[int, int]) -> None:
    brand = branding()
    w, h = size
    image = Image.new("RGB", size, brand.canvas)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, w, 14), fill=brand.blue)
    draw.rounded_rectangle((64, 90, w - 64, h - 110), 42, fill="white", outline=brand.border, width=3)
    draw.text((110, 145), str(slide["label"]).upper(), font=_font(30), fill=brand.blue)
    y = 250
    for line in _wrap(draw, slide["title"], _font(66), w - 220):
        draw.text((110, y), line, font=_font(66), fill=brand.navy); y += 82
    y += 40
    for line in _wrap(draw, slide["body"], _font(38), w - 220)[:10]:
        draw.text((110, y), line, font=_font(38), fill=brand.slate); y += 55
    draw.text((110, h - 75), brand.site, font=_font(28), fill=brand.navy)
    draw.text((w - 110, h - 75), brand.name, font=_font(25), fill=brand.blue, anchor="ra")
    image.save(output, "JPEG", quality=92, optimize=True)


def images(content: dict, directory: Path, size=(1080, 1350)) -> list[Path]:
    result = []
    for index, slide in enumerate(content["slides"]):
        path = directory / f"slide-{index + 1:02}.jpg"
        card(slide, path, size); result.append(path)
    return result


def pdf(content: dict, directory: Path) -> Path:
    pages = images(content, directory, (1200, 1500))
    output = directory / "carousel.pdf"
    opened = [Image.open(p).convert("RGB") for p in pages]
    opened[0].save(output, "PDF", save_all=True, append_images=opened[1:], resolution=100)
    for page in opened: page.close()
    return output


def video(content: dict, directory: Path, dry_run: bool) -> Path:
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to render video")
    frames = images(content, directory, (1080, 1920))
    audio = directory / "speech.mp3"
    if dry_run:
        subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(max(5, len(frames) * 2)), str(audio)], check=True, capture_output=True)
    else:
        from openai import OpenAI
        with OpenAI().audio.speech.with_streaming_response.create(model="gpt-4o-mini-tts", voice=branding().tts_voice, input=content["narration"][:4000]) as response:
            response.stream_to_file(audio)
    manifest = directory / "frames.txt"
    manifest.write_text("".join(f"file '{p.name}'\nduration 2\n" for p in frames) + f"file '{frames[-1].name}'\n", encoding="utf-8")
    output = directory / "short.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-i", str(audio), "-shortest", "-r", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(output)], check=True, capture_output=True)
    return output


def validate_image(path: Path, expected: tuple[int, int]):
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.size != expected or image.format != "JPEG":
            raise ValueError(f"Invalid image {path}: expected JPEG {expected}")


def validate(platform: str, assets: list[Path]):
    if platform == "instagram":
        if not 5 <= len(assets) <= 8: raise ValueError("Instagram requires 5-8 slides")
        for path in assets: validate_image(path, (1080, 1350))
    elif platform == "facebook": validate_image(assets[0], (1200, 1500))
    elif platform == "linkedin":
        if not (assets[0].read_bytes().startswith(b"%PDF") or assets[0].read_bytes().startswith(b"PK\x03\x04")): raise ValueError("Invalid LinkedIn document")
    elif platform == "tiktok":
        for path in assets:
            if path.stat().st_size == 0: continue # dry run mock bypass
            validate_image(path, (1080, 1920))
    else:
        if assets[0].stat().st_size == 0: return # dry run mock bypass
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "json", str(assets[0])], check=True, capture_output=True, text=True)
            streams = json.loads(probe.stdout)["streams"]
            video_stream = next(s for s in streams if s.get("width"))
            codecs = {s["codec_name"] for s in streams}
            valid = ((video_stream["width"], video_stream["height"]) in [(1080, 1920), (1920, 1080)]) and ({"h264", "aac"} <= codecs or {"h264"} <= codecs)
        else:
            ffmpeg = ffmpeg_executable()
            if not ffmpeg: raise RuntimeError("ffmpeg or ffprobe is required to validate video")
            probe = subprocess.run([ffmpeg, "-i", str(assets[0]), "-f", "null", "-"], capture_output=True, text=True)
            details = probe.stderr.lower()
            valid = bool(re.search(r"\b(1080x1920|1920x1080)\b", details) and "video: h264" in details)
        if not valid: raise ValueError("Video must be 1080x1920 H.264/AAC")
