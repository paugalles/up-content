import sys
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ..config import branding

def _font(size: int, bold=False):
    configured = branding().font_path
    if not configured:
        if sys.platform == "darwin":
            configured = "/System/Library/Fonts/Supplemental/Arial.ttf"
            if bold:
                configured = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        else:
            configured = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            if bold:
                configured = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                
    for path in (configured, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def draw_check_circle(draw, cx, cy, r, bg_color, check_color):
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=bg_color)
    pts = [
        (cx - r*0.4, cy + r*0.1),
        (cx - r*0.1, cy + r*0.4),
        (cx + r*0.5, cy - r*0.3)
    ]
    draw.line(pts, fill=check_color, width=max(1, int(r*0.25)), joint="curve")

def _wrap(draw, text, font, width):
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and draw.textlength(candidate, font=font) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        elif not paragraph:
            lines.append("")
    return lines

def generate_instagram_card(slide: dict, output: Path, size: tuple[int, int], page: int, total: int) -> None:
    brand = branding()
    w, h = size
    
    bg_color = brand.canvas
    image = Image.new("RGB", size, bg_color)
    draw = ImageDraw.Draw(image)
    
    margin_x = 80
    margin_y = 80
    
    icon_path = Path(os.getenv("BRAND_PROFILE_PATH") or "scripts/assets/brand/profile.png")
    if icon_path.exists():
        icon = Image.open(icon_path).convert("RGBA")
        icon = icon.resize((48, 48))
        image.paste(icon, (margin_x, margin_y), icon)
    
    draw.text((margin_x + 65, margin_y + 8), brand.site, font=_font(32), fill=brand.slate)
    
    page_text = f"{page}/{total}"
    page_font = _font(28)
    p_w = draw.textlength(page_text, font=page_font)
    p_h = 28
    cx, cy = w - margin_x - 30, margin_y + 24
    r = 35
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=brand.navy, width=2)
    draw.text((cx - p_w/2, cy - p_h/2 - 4), page_text, font=page_font, fill=brand.navy)
    
    title = slide.get("title", slide.get("label", ""))
    body = slide.get("body", "")
    is_first = (page == 1)
    is_last = (page == total)
    
    if is_first:
        title_font = _font(90, bold=True)
        title_lines = _wrap(draw, title, title_font, w - margin_x*2)
        body_font = _font(60, bold=True)
        body_lines = _wrap(draw, body, body_font, w - margin_x*2)
        
        total_height = len(title_lines) * 105 + 100 + len(body_lines) * 75
        y = max(180, (h + 150 - total_height) // 2)

        for line in title_lines:
            draw.text((margin_x, y), line, font=title_font, fill=brand.navy)
            y += 105
        
        y += 40
        draw.line([(margin_x, y), (margin_x + 150, y)], fill=brand.blue, width=6)
        y += 60
        
        for line in body_lines:
            draw.text((margin_x, y), line, font=body_font, fill=brand.blue)
            y += 75
            
    elif is_last:
        title_font = _font(80, bold=True)
        title_lines = _wrap(draw, title, title_font, w - margin_x*2)
        body_font = _font(45)
        body_lines = _wrap(draw, body, body_font, w - margin_x*2)
        
        total_height = len(title_lines) * 95 + 50 + len(body_lines) * 60
        y = max(180, (h - 250 + 150 - total_height) // 2)

        for line in title_lines:
            draw.text((margin_x, y), line, font=title_font, fill=brand.navy)
            y += 95
            
        y += 50
        for line in body_lines:
            draw.text((margin_x, y), line, font=body_font, fill=brand.slate)
            y += 60
            
        footer_text = f"Visit {brand.site}\nto get started"
        footer_font = _font(40, bold=True)
        f_y = h - 250
        for line in footer_text.split("\n"):
            l_w = draw.textlength(line, font=footer_font)
            draw.text(((w - l_w)/2, f_y), line, font=footer_font, fill=brand.navy)
            f_y += 55
            
    else:
        title_font = _font(70, bold=True)
        title_lines = _wrap(draw, title, title_font, w - margin_x*2)
        body_font = _font(40)
        
        paragraphs = body.split("\n")
        
        body_height = 0
        parsed_paras = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                body_height += 20
                parsed_paras.append((False, 0, [], 20))
                continue
                
            is_bullet = False
            if para.startswith("- ") or para.startswith("• "):
                is_bullet = True
                para = para[2:].strip()
                
            indent = 70 if is_bullet else 0
            available_width = w - margin_x*2 - indent
            
            lines = _wrap(draw, para, body_font, available_width)
            ph = len(lines) * 55 + 30
            body_height += ph
            parsed_paras.append((is_bullet, indent, lines, ph))
            
        total_height = len(title_lines) * 85 + 40 + body_height
        
        y = max(180, (h - 120 + 150 - total_height) // 2)

        for line in title_lines:
            draw.text((margin_x, y), line, font=title_font, fill=brand.navy)
            y += 85
            
        y += 40
        
        for is_bullet, indent, lines, ph in parsed_paras:
            if not lines:
                y += ph
                continue
                
            for i, line in enumerate(lines):
                if is_bullet and i == 0:
                    draw_check_circle(draw, margin_x + 25, y + 25, 18, brand.blue, "white")
                draw.text((margin_x + indent, y), line, font=body_font, fill=brand.slate)
                y += 55
            y += 30
            
        f_y = h - 120
        draw.text((margin_x, f_y), brand.site, font=_font(32), fill=brand.blue)
        
        ax, ay = w - margin_x - 40, f_y + 15
        aw, ah = 40, 20
        draw.line([(ax, ay), (ax + aw, ay)], fill=brand.blue, width=3)
        draw.line([(ax + aw - ah/2, ay - ah/2), (ax + aw, ay)], fill=brand.blue, width=3)
        draw.line([(ax + aw - ah/2, ay + ah/2), (ax + aw, ay)], fill=brand.blue, width=3)
        
    image.save(output, "JPEG", quality=92, optimize=True)

def generate_instagram_images(content: dict, directory: Path, size=(1080, 1350)) -> list[Path]:
    result = []
    slides = content["slides"]
    total = len(slides)
    for index, slide in enumerate(slides):
        path = directory / f"slide-{index + 1:02}.jpg"
        generate_instagram_card(slide, path, size, index + 1, total)
        result.append(path)
    return result
