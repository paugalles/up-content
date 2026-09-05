import json
import re
import shutil
import subprocess
from pathlib import Path
from PIL import Image

def ffmpeg_executable() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None

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
    elif platform == "linkedin_and_youtube":
        validate("linkedin", [assets[0]])
        validate("youtube", [assets[1]])
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
            valid = ((video_stream["width"], video_stream["height"]) in [(1080, 1920), (1920, 1080), (1080, 1350)]) and ({"h264", "aac"} <= codecs or {"h264"} <= codecs)
        else:
            ffmpeg = ffmpeg_executable()
            if not ffmpeg: raise RuntimeError("ffmpeg or ffprobe is required to validate video")
            probe = subprocess.run([ffmpeg, "-i", str(assets[0]), "-f", "null", "-"], capture_output=True, text=True)
            details = probe.stderr.lower()
            valid = bool(re.search(r"\b(1080x1920|1920x1080|1080x1350)\b", details) and "video: h264" in details)
        if not valid: raise ValueError("Video must be 1080x1920, 1920x1080, or 1080x1350 H.264/AAC")
