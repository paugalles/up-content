from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ..config import branding

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

def generate_facebook_card(slide: dict, output: Path, size: tuple[int, int]) -> None:
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
